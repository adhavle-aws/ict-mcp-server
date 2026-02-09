# mcp_server.py
from mcp.server.fastmcp import FastMCP
import boto3
import yaml
import json
import os
import time

# CRITICAL: stateless_http=True is required for AgentCore
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Expose ASGI app for AgentCore
app = mcp.streamable_http_app

def get_cfn_client():
    """Get CloudFormation client with region from environment"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    return boto3.client('cloudformation', region_name=region)

def get_bedrock_client():
    """Get Bedrock Runtime client with region from environment"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    return boto3.client('bedrock-runtime', region_name=region)


def call_bedrock_with_retry(bedrock, model_id, body, max_retries=3):
    """Call Bedrock with exponential backoff retry"""
    import time
    
    for attempt in range(max_retries):
        try:
            response = bedrock.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )
            return response
        except Exception as e:
            error_str = str(e)
            if 'ThrottlingException' in error_str or 'TooManyRequestsException' in error_str:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (0.1 * attempt)  # Exponential backoff
                    print(f"Bedrock throttled, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
            raise


@mcp.tool()
def test_delay(seconds: int = 80) -> dict:
    """
    Sleep for the given number of seconds then return. Use this to verify
    the UI/API does not timeout on long-running calls (e.g. >29s API Gateway limit).
    Default 80 seconds.

    Edge case tested: delay happens AFTER the request is sent and AFTER the
    connection is established—i.e. during server-side processing (Lambda -> AgentCore
    -> this tool). This confirms that a long-running tool execution (>29s) still
    returns a response to the client (async Lambda + post_to_connection path).
    """
    start = time.time()
    # Delay is here: during request processing, not before sending the request
    time.sleep(max(0, int(seconds)))
    elapsed = round(time.time() - start, 1)
    return {
        'success': True,
        'message': f'Completed after {elapsed} seconds (no timeout)',
        'requested_seconds': seconds,
        'actual_seconds': elapsed,
    }


def _log_timing(stage: str, tool: str, t_start: float, t_end: float = None, extra: str = ""):
    """E2E diagnostics: log duration for a stage (seconds)."""
    t_end = t_end or time.time()
    duration_s = round(t_end - t_start, 2)
    msg = f"[E2E] {tool} | {stage}: {duration_s}s"
    if extra:
        msg += f" | {extra}"
    print(msg)


@mcp.tool()
def generate_architecture_overview(prompt: str) -> dict:
    """
    Generate a comprehensive architecture overview from requirements.
    Returns markdown with reasoning, component details, and ASCII diagram with AWS icons.
    """
    t0 = time.time()
    try:
        bedrock = get_bedrock_client()
        _log_timing("setup", "generate_architecture_overview", t0)
        system_prompt = """Senior AWS Solutions Architect. Create concise architecture overviews.

OUTPUT LIMIT: Keep the entire response under 5000 tokens. Use bullet points and short paragraphs; avoid long prose, repetition, or unnecessary detail.

Include:
1. Executive Summary (2 sentences)
2. Architecture Diagram (ASCII with AWS emojis: 🌐 ALB, 🖥️ EC2, 📦 S3, 🗄️ RDS, λ Lambda, 🔐 IAM)
3. Component List (service + purpose only)


Do NOT include estimated cost, pricing, or monthly cost in the overview."""
        user_message = f"""Create a concise architecture overview (under 5000 tokens) for: {prompt}"""
        t_bedrock = time.time()
        response = call_bedrock_with_retry(
            bedrock,
            'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 5000,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            }
        )
        _log_timing("bedrock_invoke", "generate_architecture_overview", t_bedrock)
        response_body = json.loads(response['body'].read())
        overview = response_body['content'][0]['text']
        _log_timing("total", "generate_architecture_overview", t0, extra=f"output_tokens~{len(overview.split())}")
        return {'success': True, 'overview': overview}
    except Exception as e:
        _log_timing("total", "generate_architecture_overview", t0)
        return {'success': False, 'error': str(e)}


@mcp.tool()
def build_cfn_template(prompt: str, format: str = "yaml") -> dict:
    """
    Build a CloudFormation template from a natural language prompt using Claude.

    Args:
        prompt: Natural language description of the infrastructure
        format: Output format - 'json' or 'yaml' (default: yaml)

    Returns:
        dict with success status and generated CloudFormation template
    """
    t0 = time.time()
    try:
        bedrock = get_bedrock_client()
        system_prompt = """CloudFormation expert. Generate VALID, correct templates.

CRITICAL: When referencing AMI IDs via SSM Parameter Store, use ONLY these exact paths:

Amazon Linux 2023 (x86_64):
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64

Amazon Linux 2023 (ARM64):
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-arm64

Amazon Linux 2 (use standard paths under /aws/service/ami-amazon-linux-latest/ as needed).

NEVER use /aws/service/ami-amazon-linux-2023/ - this path does not exist.

CRITICAL Rules:
1. ALL resource references (Ref, GetAtt, DependsOn) MUST point to resources defined in the template
2. Check every Ref and GetAtt - ensure the resource exists
3. Use correct resource names (case-sensitive)
4. Include AWSTemplateFormatVersion: '2010-09-09'
5. Return ONLY valid YAML/JSON, no explanations

Resource identifier length limits (AWS enforces these; long names cause CREATE_FAILED):
- RDS DBInstanceIdentifier: max 63 characters. Must start with a letter; only a-z, A-Z, 0-9, hyphens. Use a SHORT value e.g. "appdb" or "mydb01", NOT stack name + "-database" (stack names can be 80+ chars).
- Same for other identifiers with 63-char limits where applicable (e.g. keep DB cluster identifiers short).

CRITICAL - Use latest supported versions (especially RDS):
- RDS: Always set EngineVersion to the latest stable minor for the chosen engine. Prefer: MySQL 8.0.43, PostgreSQL 16.x or 15.x latest, MariaDB 10.11+, Aurora MySQL 3.04+, Aurora PostgreSQL 15.x/16.x. Do NOT use deprecated or old versions (e.g. avoid MySQL 5.7, PostgreSQL 12 or older unless explicitly required).
- Lambda: Use runtime identifiers that are current (e.g. python3.12, nodejs20.x, java17).
- Other versioned resources: Prefer latest stable versions; avoid deprecated or end-of-life versions."""
        user_message = f"""Generate a CloudFormation template for: {prompt}

Format: {format.upper()}

Verify all Ref and GetAtt references point to defined resources.

Return ONLY the template."""
        t_bedrock = time.time()
        response = call_bedrock_with_retry(
            bedrock,
            'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 16384,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            }
        )
        _log_timing("bedrock_invoke", "build_cfn_template", t_bedrock)
        response_body = json.loads(response['body'].read())
        template_str = response_body['content'][0]['text'].strip()
        if template_str.startswith('```'):
            lines = template_str.split('\n')
            template_str = '\n'.join(lines[1:-1])
        _log_timing("total", "build_cfn_template", t0, extra=f"output_lines={len(template_str.splitlines())}")
        return {
            'success': True,
            'template': template_str,
            'format': format,
            'prompt': prompt
        }
    except Exception as e:
        _log_timing("total", "build_cfn_template", t0)
        return {'success': False, 'error': str(e)}


def _load_cfn_template(template_body: str):
    """Load CloudFormation template (YAML or JSON), handling intrinsic functions (!GetAtt, !Ref, etc.)."""
    if template_body.strip().startswith('{'):
        return json.loads(template_body)
    # CloudFormation YAML uses intrinsic tags (!GetAtt, !Ref, !Sub, etc.) that PyYAML doesn't know.
    # Register a constructor that treats any !... tag as plain data so we can parse for diagram.
    def _cfn_intrinsic(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        return None

    try:
        yaml.add_multi_constructor('!', _cfn_intrinsic, Loader=yaml.SafeLoader)
    except Exception:
        pass  # already registered
    return yaml.safe_load(template_body)


def _generate_diagram_png(template_body: str, output_path: str) -> int:
    """
    Parse CloudFormation template, build diagram with Python 'diagrams' package,
    write PNG to output_path. Returns number of resources drawn.
    """
    import tempfile
    orig_cwd = os.getcwd()
    from diagrams import Diagram
    from diagrams.aws.compute import Lambda, ECS, EC2
    from diagrams.aws.storage import S3
    from diagrams.aws.database import RDS, Dynamodb, ElastiCache
    from diagrams.aws.network import ELB, APIGateway, CloudFront, Route53
    from diagrams.aws.analytics import Kinesis, Athena, Glue
    from diagrams.aws.integration import SNS, SQS
    from diagrams.generic.blank import Blank

    try:
        data = _load_cfn_template(template_body)
    except Exception as e:
        raise ValueError(f"Invalid template: {e}") from e

    resources = data.get("Resources") or {}
    if not resources:
        raise ValueError("Template has no Resources")

    # Map AWS::Service::ResourceType to (diagram_module, label_prefix)
    TYPE_MAP = {
        "AWS::Lambda::Function": (Lambda, "Lambda"),
        "AWS::S3::Bucket": (S3, "S3"),
        "AWS::DynamoDB::Table": (Dynamodb, "DynamoDB"),
        "AWS::ApiGateway::RestApi": (APIGateway, "API"),
        "AWS::ApiGatewayV2::Api": (APIGateway, "API"),
        "AWS::ElasticLoadBalancingV2::LoadBalancer": (ELB, "ALB"),
        "AWS::ECS::Service": (ECS, "ECS"),
        "AWS::ECS::Cluster": (ECS, "Cluster"),
        "AWS::EC2::Instance": (EC2, "EC2"),
        "AWS::RDS::DBInstance": (RDS, "RDS"),
        "AWS::ElastiCache::CacheCluster": (ElastiCache, "ElastiCache"),
        "AWS::CloudFront::Distribution": (CloudFront, "CloudFront"),
        "AWS::Route53::HostedZone": (Route53, "Route53"),
        "AWS::Kinesis::Stream": (Kinesis, "Kinesis"),
        "AWS::KinesisFirehose::DeliveryStream": (Kinesis, "Firehose"),
        "AWS::Athena::WorkGroup": (Athena, "Athena"),
        "AWS::Glue::Job": (Glue, "Glue"),
        "AWS::Glue::Crawler": (Glue, "Crawler"),
        "AWS::Glue::Database": (Glue, "GlueDB"),
        "AWS::SNS::Topic": (SNS, "SNS"),
        "AWS::SQS::Queue": (SQS, "SQS"),
        "AWS::StepFunctions::StateMachine": (Blank, "StepFunctions"),
    }

    # Collect dependencies for edges (Ref and simple DependsOn)
    def get_refs(props):
        refs = []
        if not isinstance(props, dict):
            return refs
        if "Ref" in props and isinstance(props["Ref"], str):
            refs.append(props["Ref"])
        for v in props.values():
            if isinstance(v, dict):
                refs.extend(get_refs(v))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        refs.extend(get_refs(item))
        return refs

    # diagrams writes to cwd; use output_dir and a fixed name so we know the path
    output_dir = os.path.dirname(output_path)
    output_basename = os.path.basename(output_path).replace(".png", "")
    try:
        os.chdir(output_dir)
        diagram_filename = output_basename
    except Exception:
        diagram_filename = output_path.replace(".png", "")

    nodes = {}
    with Diagram(
        "Architecture",
        filename=diagram_filename,
        direction="LR",
        show=False,
        outformat="png",
    ):
        for logical_id, config in resources.items():
            if not isinstance(config, dict):
                continue
            res_type = config.get("Type", "")
            props = config.get("Properties") or {}
            depends_on = config.get("DependsOn")
            if isinstance(depends_on, str):
                depends_on = [depends_on]
            elif depends_on is None:
                depends_on = []

            pair = TYPE_MAP.get(res_type)
            if pair is None:
                node_cls, prefix = Blank, "Resource"
            else:
                node_cls, prefix = pair
            label = logical_id if len(logical_id) <= 24 else logical_id[:21] + "..."
            try:
                node = node_cls(label)
            except Exception:
                node = Blank(label)
            nodes[logical_id] = node

        # Edges from DependsOn and Ref
        for logical_id, config in resources.items():
            if not isinstance(config, dict):
                continue
            src = nodes.get(logical_id)
            if src is None:
                continue
            deps = list(config.get("DependsOn") or []) if isinstance(config.get("DependsOn"), list) else []
            if isinstance(config.get("DependsOn"), str):
                deps = [config.get("DependsOn")]
            for ref in get_refs(config.get("Properties") or {}):
                if ref in nodes and ref != logical_id:
                    deps.append(ref)
            for dep in deps:
                if dep in nodes:
                    try:
                        nodes[dep] >> src
                    except Exception:
                        pass

    try:
        os.chdir(orig_cwd)
    except Exception:
        pass
    return len(nodes)


@mcp.tool()
def generate_architecture_diagram(template_body: str) -> dict:
    """
    Generate a professional architecture diagram from a CloudFormation template
    (Infrastructure Composer-style). Parses the template, maps AWS resources to
    official icons, and returns a PNG image as base64.
    """
    import base64
    import tempfile
    import os

    if not template_body or not template_body.strip():
        return {"success": False, "error": "template_body is required"}

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        try:
            count = _generate_diagram_png(template_body, tmp_path)
            with open(tmp_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
            return {
                "success": True,
                "image": image_b64,
                "format": "png",
                "encoding": "base64",
                "resources_count": count,
            }
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            dot_path = tmp_path.replace(".png", "")
            for path in [dot_path + ".png", dot_path]:
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def validate_cfn_template(template_body: str, auto_fix: bool = True) -> dict:
    """
    Validate and optionally auto-fix CloudFormation template.
    
    Args:
        template_body: CloudFormation template (YAML or JSON)
        auto_fix: If True, automatically fix validation errors using Claude (default: True)
    
    Returns:
        dict with validation results and fixed template if auto_fix is enabled
    """
    cfn = get_cfn_client()
    
    try:
        # Try to validate
        response = cfn.validate_template(TemplateBody=template_body)
        template_params = []
        for p in response.get('Parameters', []):
            template_params.append({
                'parameter_key': p.get('ParameterKey', ''),
                'default_value': p.get('DefaultValue', ''),
                'no_echo': p.get('NoEcho', False),
                'description': p.get('Description', '')
            })
        return {
            'success': True,
            'valid': True,
            'capabilities': response.get('Capabilities', []),
            'parameters': template_params,
            'template': template_body,
            'fixed': False
        }
    except Exception as e:
        error_message = str(e)
        
        # If auto_fix is disabled, just return the error
        if not auto_fix:
            return {
                'success': False,
                'valid': False,
                'error': error_message
            }
        
        # Auto-fix: Use Claude to fix the template
        try:
            bedrock = get_bedrock_client()
            
            system_prompt = """CloudFormation expert. Fix validation errors.

Rules:
1. Check all resource references (Ref, GetAtt, DependsOn)
2. Ensure referenced resources exist
3. Fix resource names and dependencies
4. When touching RDS (AWS::RDS::DBInstance, AWS::RDS::DBCluster): set EngineVersion to latest stable (e.g. MySQL 8.0.43, PostgreSQL 16.x/15.x, Aurora 3.04+). Avoid deprecated versions.
5. Return ONLY the fixed template
6. No explanations"""

            user_message = f"""Fix this CloudFormation validation error:

ERROR: {error_message}

TEMPLATE:
{template_body}

Common fixes:
- If resource not found: Check spelling, add missing resource, or remove reference
- If GetAtt fails: Verify resource exists and attribute is valid
- If DependsOn fails: Ensure dependency resource exists
- For RDS: Use latest EngineVersion (e.g. MySQL 8.0.43, PostgreSQL 16.x); do not leave old or deprecated versions.

Return ONLY the corrected template."""

            response = call_bedrock_with_retry(
                bedrock,
                'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
                {
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 16384,  # Match template generation
                    'system': system_prompt,
                    'messages': [{'role': 'user', 'content': user_message}]
                }
            )
            
            response_body = json.loads(response['body'].read())
            fixed_template = response_body['content'][0]['text'].strip()
            
            # Clean up markdown code blocks
            if fixed_template.startswith('```'):
                lines = fixed_template.split('\n')
                fixed_template = '\n'.join(lines[1:-1])
            
            # Validate the fixed template
            try:
                cfn.validate_template(TemplateBody=fixed_template)
                return {
                    'success': True,
                    'valid': True,
                    'fixed': True,
                    'original_error': error_message,
                    'template': fixed_template,
                    'message': 'Template automatically fixed and validated successfully!'
                }
            except Exception as revalidation_error:
                return {
                    'success': False,
                    'valid': False,
                    'fixed': False,
                    'error': f'Auto-fix attempted but validation still failed: {str(revalidation_error)}',
                    'original_error': error_message,
                    'template': fixed_template
                }
                
        except Exception as fix_error:
            return {
                'success': False,
                'valid': False,
                'error': f'Validation failed: {error_message}. Auto-fix failed: {str(fix_error)}'
            }


@mcp.tool()
def provision_cfn_stack(
    stack_name: str,
    template_body: str,
    capabilities: list = None,
    parameters: list = None,
) -> dict:
    """
    Create or update a CloudFormation stack.

    Args:
        stack_name: Name of the stack.
        template_body: CloudFormation template (YAML or JSON).
        capabilities: Optional list of capabilities (e.g. CAPABILITY_NAMED_IAM).
        parameters: Optional list of parameter dicts, each with ParameterKey and ParameterValue.
                   Example: [{"ParameterKey": "DBPassword", "ParameterValue": "secret"}]
    """
    cfn = get_cfn_client()
    try:
        # Check if stack exists
        try:
            cfn.describe_stacks(StackName=stack_name)
            stack_exists = True
        except Exception:
            stack_exists = False

        params = {
            'StackName': stack_name,
            'TemplateBody': template_body,
        }

        # Tag stacks created by this MCP so they're identifiable in billing, DevOps Agent, and ops.
        if not stack_exists:
            params['Tags'] = [
                {'Key': 'stack-creator', 'Value': 'aws-architect-mcp'},
            ]

        if capabilities:
            params['Capabilities'] = capabilities

        if parameters:
            params['Parameters'] = [
                {'ParameterKey': p.get('ParameterKey'), 'ParameterValue': str(p.get('ParameterValue', ''))}
                for p in parameters
                if p.get('ParameterKey')
            ]

        if stack_exists:
            response = cfn.update_stack(**params)
            action = 'updated'
        else:
            response = cfn.create_stack(**params)
            action = 'created'

        return {
            'success': True,
            'action': action,
            'stack_id': response['StackId'],
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }


@mcp.tool()
def delete_cfn_stack(stack_name: str) -> dict:
    """Delete a CloudFormation stack by name."""
    cfn = get_cfn_client()
    try:
        cfn.delete_stack(StackName=stack_name)
        return {'success': True, 'message': f'Stack {stack_name} deletion started'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@mcp.tool()
def get_cfn_stack_events(stack_name: str, limit: int = 30) -> dict:
    """
    Get current stack status, recent events, and stack outputs for progress display.
    Returns stack_status, events (newest first), and outputs when stack is in a complete state.
    Poll this to show live progress. Outputs are included so the UI can render them when complete.
    """
    cfn = get_cfn_client()
    try:
        desc = cfn.describe_stacks(StackName=stack_name)
        stack = desc['Stacks'][0]
        stack_status = stack['StackStatus']
        events_resp = cfn.describe_stack_events(StackName=stack_name)
        events = []
        for ev in events_resp.get('StackEvents', [])[:limit]:
            events.append({
                'timestamp': str(ev.get('Timestamp', '')),
                'resource_status': ev.get('ResourceStatus', ''),
                'resource_type': ev.get('ResourceType', ''),
                'logical_id': ev.get('LogicalResourceId', ''),
                'status_reason': ev.get('ResourceStatusReason') or ''
            })
        outputs = []
        for out in stack.get('Outputs', []):
            outputs.append({
                'output_key': out.get('OutputKey', ''),
                'output_value': out.get('OutputValue', ''),
                'description': out.get('Description') or ''
            })
        return {
            'success': True,
            'stack_status': stack_status,
            'events': events,
            'outputs': outputs
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'stack_status': None, 'events': [], 'outputs': []}


@mcp.tool()
def analyze_cost_optimization(prompt: str = None, template_body: str = None) -> dict:
    """
    Analyze cost optimization opportunities from requirements or CloudFormation template.
    """
    try:
        if not prompt and not template_body:
            return {'success': False, 'error': 'Either prompt or template_body must be provided'}
        
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS cost optimization expert. Analyze architectures and provide specific, actionable cost-saving recommendations that directly reference the components and findings provided.

Reference specific recommendations and risks identified. Provide concrete cost estimates and savings calculations."""

        if template_body:
            user_message = f"""Analyze this CloudFormation template for cost optimization:

{template_body}

Provide:
1. Cost Analysis: Estimate monthly costs for SPECIFIC resources in the template
2. Cost Drivers: Identify the most expensive components by name
3. Optimization Recommendations: Reference specific resources and provide alternatives
4. Estimated Savings: Provide dollar amounts or percentages
5. Implementation Priority: High/Medium/Low with justification

Be specific - reference actual resource names and provide cost estimates."""
        elif prompt:
            user_message = f"""Analyze cost optimization based on this architecture review:

ARCHITECTURE FINDINGS:
{prompt}

Based on the architecture and findings above, provide:

1. Cost Analysis:
   - Estimated monthly costs for the components mentioned (ALB, EC2, RDS, NAT Gateway, etc.)
   - Break down by service
   - Consider the specific configurations mentioned (Multi-AZ, Auto Scaling, etc.)

2. Cost Drivers:
   - Identify the 3 most expensive components
   - Explain why they're costly in THIS specific architecture

3. Optimization Recommendations:
   - Reference the specific findings above
   - Provide alternatives for expensive components
   - Consider the trade-offs mentioned (reliability vs cost)

4. Estimated Savings:
   - Provide specific dollar amounts or percentages
   - Show before/after cost comparison

5. Implementation Roadmap:
   - Quick wins (< 1 week)
   - Medium-term optimizations (1-4 weeks)
   - Long-term strategies (1-3 months)

IMPORTANT: Reference the specific architecture components and findings. Don't provide generic cost advice."""

        response = call_bedrock_with_retry(
            bedrock,
            'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            }
        )
        
        response_body = json.loads(response['body'].read())
        analysis = response_body['content'][0]['text']
        
        return {
            'success': True,
            'analysis': analysis
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@mcp.tool()
def well_architected_review(prompt: str = None, template_body: str = None) -> dict:
    """
    Perform architecture review on requirements or CloudFormation template
    (operational excellence, security, reliability, performance, cost, sustainability).
    """
    try:
        if not prompt and not template_body:
            return {'success': False, 'error': 'Either prompt or template_body must be provided'}
        
        bedrock = get_bedrock_client()
        
        system_prompt = """AWS architecture expert. Review against operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability. Give specific recommendations."""

        if template_body:
            user_message = f"""Review CloudFormation template:

{template_body}

For each area: Assessment, Risks, Recommendations (High/Medium/Low priority)"""
        elif prompt:
            user_message = f"""Review architecture:

{prompt}

For each area: Assessment, Strengths, Risks, Recommendations (priority)"""

        response = call_bedrock_with_retry(
            bedrock,
            'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 1500,  # Reduced from 4096
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            }
        )
        
        response_body = json.loads(response['body'].read())
        review = response_body['content'][0]['text']
        
        return {
            'success': True,
            'review': review
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
