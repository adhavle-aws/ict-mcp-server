# mcp_server.py
from mcp.server.fastmcp import FastMCP
import boto3
import yaml
import json
import os
import time

# CRITICAL: stateless_http=True is required for AgentCore
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Bedrock model for overview/cost/WAF/fix (override with BEDROCK_MODEL_ID env).
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "global.anthropic.claude-haiku-4-5-20251001-v1:0",
)
# Model for CFN template generation only (override with BEDROCK_MODEL_ID_CFN_BUILDER env). Default: same as BEDROCK_MODEL_ID (Claude Haiku 4.5).
BEDROCK_MODEL_ID_CFN_BUILDER = os.environ.get(
    "BEDROCK_MODEL_ID_CFN_BUILDER",
    BEDROCK_MODEL_ID,
)

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


def _extract_text_from_converse_response(response):
    """Extract assistant text from Bedrock Converse API response."""
    out = _extract_content_from_converse_response(response)
    return out["text"]


def _normalize_thinking_value(value):
    """Extract reasoning text string from thinking block (may be str or dict with reasoningText.text)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        rt = value.get("reasoningText") or value.get("reasoningContent")
        if isinstance(rt, dict) and "text" in rt:
            return rt["text"]
        if isinstance(rt, str):
            return rt
    return ""


def _extract_content_from_converse_response(response):
    """Extract text and thinking (reasoning) from Bedrock Converse API response.
    Returns dict with keys: text (str), thinking (str). Thinking may be empty."""
    content = response.get("output", {}).get("message", {}).get("content") or []
    text_parts = []
    thinking_parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if "text" in block:
            text_parts.append(block["text"])
        # Extended thinking: block has "thinking" (Anthropic) or "reasoningContent" (Bedrock ContentBlock)
        if "thinking" in block:
            thinking_parts.append(_normalize_thinking_value(block["thinking"]))
        if "reasoningContent" in block:
            thinking_parts.append(_normalize_thinking_value(block["reasoningContent"]))
    return {"text": "".join(text_parts), "thinking": "".join(thinking_parts)}


def converse_with_retry(bedrock, model_id, system_prompt, user_message, max_tokens=4096, max_retries=3, enable_thinking=True, thinking_budget=4096, temperature=None, top_p=None, top_k=None):
    """Call Bedrock Converse API with exponential backoff retry. Returns the raw response dict.
    When enable_thinking=True: uses extended thinking (CoT) via additionalModelRequestFields; temperature omitted.
    When enable_thinking=False: no thinking, uses temperature (default 0.2) for faster/simpler tasks.
    thinking_budget: max tokens for reasoning when enable_thinking=True (min 1024).
    temperature: 0 = most consistent, higher = more diverse (only when enable_thinking=False).
    top_p: inferenceConfig topP (0-1); top_k: passed via additionalModelRequestFields when set (e.g. 1 for consistent)."""
    if enable_thinking:
        inference_config = {"maxTokens": max_tokens}
        additional = {"thinking": {"type": "enabled", "budget_tokens": max(1024, thinking_budget)}}
    else:
        inference_config = {"maxTokens": max_tokens, "temperature": temperature if temperature is not None else 0.2}
        # Model allows temperature OR top_p, not both—only add topP when not overriding temperature
        if top_p is not None and temperature is None:
            inference_config["topP"] = top_p
        additional = {"top_k": top_k} if top_k is not None else None
    for attempt in range(max_retries):
        try:
            kwargs = {
                "modelId": model_id,
                "messages": [{"role": "user", "content": [{"text": user_message}]}],
                "system": [{"text": system_prompt}],
                "inferenceConfig": inference_config,
            }
            if additional is not None:
                kwargs["additionalModelRequestFields"] = additional
            # Latency-optimized inference (when supported for model/region). See docs/COLD_START_AND_PREWARM.md
            if os.environ.get("BEDROCK_LATENCY_OPTIMIZED", "").lower() == "true":
                kwargs["performanceConfig"] = {"latency": "optimized"}
            response = bedrock.converse(**kwargs)
            return response
        except Exception as e:
            error_str = str(e)
            if "ThrottlingException" in error_str or "TooManyRequestsException" in error_str:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (0.1 * attempt)
                    print(f"Bedrock throttled, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
            raise


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
    Returns markdown with reasoning and component details.
    """
    t0 = time.time()
    try:
        bedrock = get_bedrock_client()
        _log_timing("setup", "generate_architecture_overview", t0)
        system_prompt = """Senior AWS Solutions Architect. Create a short architecture overview.

Keep response under 800 tokens. Use bullet points only.
Include: (1) Executive Summary in 2 sentences (2) Component list: service + one-line purpose.
Do NOT include cost, pricing, or monthly estimates. Do NOT include a "Key Design Decisions" section."""
        user_message = f"""Short architecture overview for: {prompt}"""
        t_bedrock = time.time()
        # No extended thinking for this tool = faster first response; other tools keep CoT.
        response = converse_with_retry(
            bedrock, BEDROCK_MODEL_ID, system_prompt, user_message, max_tokens=1024, enable_thinking=False
        )
        _log_timing("bedrock_invoke", "generate_architecture_overview", t_bedrock)
        out = _extract_content_from_converse_response(response)
        overview = out["text"]
        _log_timing("total", "generate_architecture_overview", t0, extra=f"output_tokens~{len(overview.split())}")
        result = {'success': True, 'overview': overview}
        if out.get("thinking"):
            result["thinking"] = out["thinking"]
        return result
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
        print("[build_cfn_template] enable_thinking=False (speed-optimized)")
        # Condensed prompt: same rules, fewer tokens for faster input and focused output
        system_prompt = """CloudFormation expert. Generate VALID templates only.
AMI paths (SSM): Use ONLY /aws/service/ami-amazon-linux-latest/ (e.g. al2023-ami-kernel-6.1-x86_64, al2023-ami-kernel-6.1-arm64). NEVER /aws/service/ami-amazon-linux-2023/.

Rules: (1) Every Ref, GetAtt, DependsOn must reference a resource defined in this template. (2) AWSTemplateFormatVersion: '2010-09-09'. (3) Return ONLY YAML or JSON, no commentary.
Identifiers: RDS DBInstanceIdentifier max 63 chars, start with letter; use short names e.g. "appdb", "mydb01".
Versions: RDS use latest stable (MySQL 8.0.43, PostgreSQL 16.x/15.x, Aurora 3.04+). Lambda use python3.12, nodejs20.x. No deprecated versions."""
        user_message = f"""Generate a CloudFormation template for: {prompt}

Format: {format.upper()}. Verify every Ref and GetAtt points to a defined resource. Return ONLY the template."""
        t_bedrock = time.time()
        # CRITICAL: enable_thinking=False for speed. With thinking this tool takes 60-70s; without, ~15-35s.
        response = converse_with_retry(
            bedrock, BEDROCK_MODEL_ID, system_prompt, user_message, max_tokens=25000, enable_thinking=False
        )
        _log_timing("bedrock_invoke", "build_cfn_template", t_bedrock)
        out = _extract_content_from_converse_response(response)
        template_str = out["text"].strip()
        if template_str.startswith('```'):
            lines = template_str.split('\n')
            template_str = '\n'.join(lines[1:-1])
        _log_timing("total", "build_cfn_template", t0, extra=f"output_lines={len(template_str.splitlines())}")
        result = {
            'success': True,
            'template': template_str,
            'format': format,
            'prompt': prompt
        }
        if out.get("thinking"):
            result["thinking"] = out["thinking"]
        return result
    except Exception as e:
        _log_timing("total", "build_cfn_template", t0)
        return {'success': False, 'error': str(e)}


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

            response = converse_with_retry(
                bedrock, BEDROCK_MODEL_ID, system_prompt, user_message, max_tokens=16384
            )
            out = _extract_content_from_converse_response(response)
            fixed_template = out["text"].strip()
            
            # Clean up markdown code blocks
            if fixed_template.startswith('```'):
                lines = fixed_template.split('\n')
                fixed_template = '\n'.join(lines[1:-1])
            
            # Validate the fixed template
            try:
                cfn.validate_template(TemplateBody=fixed_template)
                result = {
                    'success': True,
                    'valid': True,
                    'fixed': True,
                    'original_error': error_message,
                    'template': fixed_template,
                    'message': 'Template automatically fixed and validated successfully!'
                }
                if out.get("thinking"):
                    result["thinking"] = out["thinking"]
                return result
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
