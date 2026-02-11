# mcp_server.py
from mcp.server.fastmcp import FastMCP
import boto3
import yaml
import json
import os
import re
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
# Read-only mode: when set (MCP_READONLY=true), provision_cfn_stack and delete_cfn_stack return an error (no mutating actions).
READONLY_MODE = os.environ.get("MCP_READONLY", "").lower() in ("true", "1", "yes")

# Expose ASGI app for AgentCore
app = mcp.streamable_http_app

def get_cfn_client(region=None):
    """Get CloudFormation client; region from arg or env."""
    region = region or os.environ.get('AWS_REGION', 'us-east-1')
    return boto3.client('cloudformation', region_name=region)


def get_ec2_client(region=None):
    """Get EC2 client; region from arg or env."""
    region = region or os.environ.get('AWS_REGION', 'us-east-1')
    return boto3.client('ec2', region_name=region)


# Hardcoded VPC for demo when default VPC is not available (or to force this VPC).
HARDCODED_DEFAULT_VPC_ID = "vpc-0ca2fc76"


def _get_subnet_ids_for_vpc(vpc_id: str, region=None):
    """Return list of subnet IDs for the given VPC."""
    try:
        ec2 = get_ec2_client(region=region)
        subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]).get('Subnets', [])
        return [s['SubnetId'] for s in subnets]
    except Exception:
        return []


def _get_default_vpc_and_subnets(region=None):
    """Return (vpc_id, list of subnet_ids) for the default VPC, or hardcoded demo VPC, or (None, []) if none."""
    try:
        ec2 = get_ec2_client(region=region)
        vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}]).get('Vpcs', [])
        if vpcs:
            vpc_id = vpcs[0]['VpcId']
            subnet_ids = _get_subnet_ids_for_vpc(vpc_id, region=region)
            return vpc_id, subnet_ids
        # Fallback to hardcoded demo VPC
        subnet_ids = _get_subnet_ids_for_vpc(HARDCODED_DEFAULT_VPC_ID, region=region)
        if subnet_ids:
            return HARDCODED_DEFAULT_VPC_ID, subnet_ids
        return None, []
    except Exception:
        return None, []


def _normalize_cfn_template_for_provision(template_body: str) -> str:
    """Strip invalid keys from template so provision succeeds (e.g. ScaleInCooldown/ScaleOutCooldown inside TargetTrackingConfiguration; LoggingLevel/DataTraceEnabled at AWS::ApiGateway::Stage root; Tags inside CloudFront DistributionConfig)."""
    try:
        is_json = template_body.strip().startswith('{')
        if is_json:
            doc = json.loads(template_body)
            resources = doc.get('Resources') or {}
            changed = False
            for rdef in resources.values():
                if not isinstance(rdef, dict):
                    continue
                rtype = rdef.get('Type')
                props = rdef.get('Properties') or {}
                if rtype == 'AWS::AutoScaling::ScalingPolicy':
                    tt = props.get('TargetTrackingConfiguration')
                    if isinstance(tt, dict):
                        for key in ('ScaleInCooldown', 'ScaleOutCooldown'):
                            if key in tt:
                                del tt[key]
                                changed = True
                elif rtype == 'AWS::ApiGateway::Stage':
                    for key in ('LoggingLevel', 'DataTraceEnabled'):
                        if key in props:
                            del props[key]
                            changed = True
                elif rtype == 'AWS::CloudFront::Distribution':
                    dist_cfg = props.get('DistributionConfig')
                    if isinstance(dist_cfg, dict) and 'Tags' in dist_cfg:
                        tags = dist_cfg.pop('Tags')
                        if tags is not None and 'Tags' not in props:
                            props['Tags'] = tags
                        changed = True
            if changed:
                return json.dumps(doc, indent=2)
            return template_body
        # YAML: remove ScaleInCooldown/ScaleOutCooldown lines (avoid full round-trip to preserve !Ref etc.)
        # ApiGateway Stage LoggingLevel/DataTraceEnabled stripping is done only in JSON path above
        lines = template_body.splitlines()
        out = []
        changed = False
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith('ScaleInCooldown:') or stripped.startswith('ScaleOutCooldown:'):
                changed = True
                i += 1
                if i < len(lines):
                    next_indent = len(lines[i]) - len(lines[i].lstrip()) if lines[i] else 0
                    curr_indent = len(line) - len(line.lstrip()) if line else 0
                    if next_indent > curr_indent and lines[i].strip():
                        i += 1
                continue
            out.append(line)
            i += 1
        return '\n'.join(out) if changed else template_body
    except Exception:
        return template_body


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


def converse_with_retry(bedrock, model_id, system_prompt, user_message, max_tokens=4096, max_retries=3, enable_thinking=True, thinking_budget=4096, temperature=None, top_p=None, top_k=None, system_cache_ttl=None):
    """Call Bedrock Converse API with exponential backoff retry. Returns the raw response dict.
    When enable_thinking=True: uses extended thinking (CoT) via additionalModelRequestFields; temperature omitted.
    When enable_thinking=False: no thinking, uses temperature (default 0.2) for faster/simpler tasks.
    thinking_budget: max tokens for reasoning when enable_thinking=True (min 1024).
    temperature: 0 = most consistent, higher = more diverse (only when enable_thinking=False).
    top_p: inferenceConfig topP (0-1); top_k: passed via additionalModelRequestFields when set (e.g. 1 for consistent).
    system_cache_ttl: optional '5m' or '1h' to enable Converse prompt caching for the system block (cachePoint); None = no cache."""
    if enable_thinking:
        inference_config = {"maxTokens": max_tokens}
        additional = {"thinking": {"type": "enabled", "budget_tokens": max(1024, thinking_budget)}}
    else:
        inference_config = {"maxTokens": max_tokens, "temperature": temperature if temperature is not None else 0.2}
        # Model allows temperature OR top_p, not both—only add topP when not overriding temperature
        if top_p is not None and temperature is None:
            inference_config["topP"] = top_p
        additional = {"top_k": top_k} if top_k is not None else None
    # Converse API uses cachePoint (not cache_control). System is array: text block then optional cachePoint block.
    system_blocks = [{"text": system_prompt}]
    if system_cache_ttl in ("5m", "1h"):
        system_blocks.append({"cachePoint": {"type": "default", "ttl": system_cache_ttl}})
    for attempt in range(max_retries):
        try:
            kwargs = {
                "modelId": model_id,
                "messages": [{"role": "user", "content": [{"text": user_message}]}],
                "system": system_blocks,
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


# In-memory cache for CloudFormation resource schemas (describe_type) to avoid repeated API calls
_resource_schema_cache = {}

# Resource types to fetch schema for and inject into build_cfn_template (reduces deploy failures)
_KEY_SCHEMA_TYPES_FOR_BUILDER = ["AWS::RDS::DBInstance", "AWS::EC2::LaunchTemplate"]


def _schema_summary_for_builder(resource_type: str, max_chars: int = 2000) -> str:
    """Fetch schema for resource_type and return a short summary (required + property names) for the template builder."""
    result = get_resource_schema_information(resource_type)
    if not result.get("success") or not result.get("schema"):
        return f"{resource_type}: (schema unavailable: {result.get('error', 'unknown')})"
    schema = result["schema"]
    parts = [f"{resource_type}:"]
    if isinstance(schema.get("required"), list) and schema["required"]:
        parts.append(f"  required: {schema['required']}")
    props = schema.get("properties")
    if isinstance(props, dict):
        keys = list(props.keys())[:50]
        parts.append(f"  properties (sample): {keys}")
    return "\n".join(parts)[:max_chars]


@mcp.tool()
def get_resource_schema_information(resource_type: str, region: str = None) -> dict:
    """
    Get CloudFormation schema for an AWS resource type. Use this to ensure templates use
    correct property names, types, and required fields — reduces deploy failures.

    Args:
        resource_type: AWS resource type (e.g. "AWS::S3::Bucket", "AWS::RDS::DBInstance",
                       "AWS::EC2::LaunchTemplate", "AWS::Lambda::Function").
        region: Optional AWS region (default: from AWS_REGION env or us-east-1).

    Returns:
        dict with schema from CloudFormation describe_type (JSON schema for the resource).
        Use it when building or fixing templates to match exact property names and constraints.
    """
    if not resource_type or not resource_type.strip():
        return {"success": False, "error": "resource_type is required (e.g. AWS::S3::Bucket)"}
    resource_type = resource_type.strip()
    cache_key = f"{region or 'default'}:{resource_type}"
    if cache_key in _resource_schema_cache:
        return {"success": True, "resource_type": resource_type, "schema": _resource_schema_cache[cache_key], "cached": True}
    cfn = get_cfn_client(region=region)
    try:
        resp = cfn.describe_type(Type="RESOURCE", TypeName=resource_type)
        schema_str = resp.get("Schema")
        if not schema_str:
            return {"success": False, "error": f"No schema returned for {resource_type}"}
        schema = json.loads(schema_str)
        _resource_schema_cache[cache_key] = schema
        return {"success": True, "resource_type": resource_type, "schema": schema, "cached": False}
    except Exception as e:
        return {"success": False, "error": str(e), "resource_type": resource_type}


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
        # CFN template builder tool: deployable templates with defaults, Secrets Manager, no Cognito
        system_prompt = """CloudFormation expert. CFN template builder tool. Generate VALID, DEPLOYABLE templates only.
Templates must deploy successfully with ZERO manual input — all parameters must have default values.

CRITICAL — NO NEW VPC:
You MUST NOT create any of these resources: AWS::EC2::VPC, AWS::EC2::Subnet, AWS::EC2::InternetGateway, AWS::EC2::VPCGatewayAttachment, AWS::EC2::NATGateway, AWS::EC2::EIP, AWS::EC2::RouteTable, AWS::EC2::Route, AWS::EC2::SubnetRouteTableAssociation. Account VPC limits are often reached. Instead, ALWAYS use Parameters: VpcId (AWS::EC2::VPC::Id), PublicSubnetIds (List<AWS::EC2::Subnet::Id>), PrivateSubnetIds (List<AWS::EC2::Subnet::Id>). Reference them with !Ref VpcId, !Ref PublicSubnetIds, !Ref PrivateSubnetIds. Do not include a Resources section for VPC, Subnet, IGW, NAT, or Route — only parameters.

TEMPLATE STRUCTURE:
(1) AWSTemplateFormatVersion: '2010-09-09'
(2) Always include Description
(3) Return ONLY YAML, no commentary, no markdown code blocks
(4) Every Ref, Fn::GetAtt, DependsOn must reference a resource defined in this template
(5) No circular dependencies between resources
(6) Keep all resource names under 32 characters where AWS enforces it (ALB Name, Target Group Name) — omit Name or use short literal; never use stack name for these

PARAMETERS (CRITICAL — every parameter MUST have a Default value):
(1) EVERY parameter must include a Default value so the template deploys without manual input
(2) For environment: Default: 'dev' with AllowedValues: [dev, staging, prod]
(3) For instance types: Default: 't3.micro' for dev, 't3.medium' for prod
(4) Do NOT add parameters for VPC CIDR or subnet CIDRs — we never create VPC/Subnets; use Parameters VpcId, PublicSubnetIds, PrivateSubnetIds only.
(6) For allocated storage: Default: '20' (minimum for gp3)
(7) For names: Default using descriptive short names
(8) For ports: Default appropriate port (5432 for PostgreSQL, 443 for HTTPS, 80 for HTTP)
(9) For retention periods: Default: 7
(10) For scaling: MinSize Default 1, MaxSize Default 3, DesiredCapacity Default 1

PASSWORD AND SECRET HANDLING:
(1) PREFERRED: Use AWS::SecretsManager::Secret with GenerateSecretString to auto-generate credentials:
    DBSecret:
      Type: AWS::SecretsManager::Secret
      Properties:
        Name: !Sub '${AWS::StackName}-db-secret'
        Description: Auto-generated database credentials
        GenerateSecretString:
          SecretStringTemplate: '{"username": "dbadmin"}'
          GenerateStringKey: password
          PasswordLength: 24
          ExcludePunctuation: false
          ExcludeCharacters: '"@/\\'
        Tags:
          - Key: stack-creator
            Value: aws-architect-mcp
          - Key: project
            Value: mwc-demo
    Then reference in RDS:
      MasterUsername: !Sub '{{resolve:secretsmanager:${DBSecret}:SecretString:username}}'
      MasterUserPassword: !Sub '{{resolve:secretsmanager:${DBSecret}:SecretString:password}}'
(2) ALTERNATIVE: ManageMasterUserPassword: true on RDS to let Secrets Manager handle it automatically
(3) FALLBACK ONLY: If neither Secrets Manager pattern is used, create a password parameter with:
    - NoEcho: true
    - MinLength: 12
    - MaxLength: 41
    - AllowedPattern: '^[a-zA-Z][a-zA-Z0-9@#$%^&+=]*$'
    - ConstraintDescription: 'Must start with a letter. 12-41 chars. Alphanumeric and @#$%^&+= only.'
    - Default: 'ChangeMe12345!' with Description saying 'Default for dev — CHANGE FOR PRODUCTION'
(4) NEVER leave a password parameter without a default — it blocks automated deployment
(5) For API keys or tokens: always use AWS::SecretsManager::Secret with GenerateSecretString
(6) AWS::SecretsManager::Secret: to get the ARN use !Ref SecretResource (Ref returns the ARN). Do NOT use !GetAtt SecretResource.Arn — Arn does not exist in the schema and causes "Requested attribute Arn does not exist in schema".

PARAMETER TEMPLATE (use this pattern for all templates):
  Parameters:
    Environment:
      Type: String
      Default: dev
      AllowedValues: [dev, staging, prod]
      Description: Deployment environment
    InstanceType:
      Type: String
      Default: t3.micro
      AllowedValues: [t3.micro, t3.small, t3.medium, t3.large]
      Description: EC2 instance type
    LatestAmiId:
      Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
      Default: /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64
      Description: Latest Amazon Linux 2023 AMI
    VpcId:
      Type: AWS::EC2::VPC::Id
      Description: Existing VPC ID (use default VPC for demo)
    PublicSubnetIds:
      Type: List<AWS::EC2::Subnet::Id>
      Description: At least 2 subnet IDs for ALB (e.g. default VPC subnets)
    PrivateSubnetIds:
      Type: List<AWS::EC2::Subnet::Id>
      Description: At least 2 subnet IDs for ASG and RDS (for default VPC use same as PublicSubnetIds)
    DBInstanceIdentifierSuffix:
      Type: String
      Default: appdb
      Description: Suffix for RDS identifier (appDB-{suffix}). Provisioner auto-fills a short unique value (e.g. last 8 digits of timestamp) when not overridden — keeps names unique and under 63 chars.
    BucketNameSuffix:
      Type: String
      Default: files
      Description: Suffix for S3 bucket name (app-{AccountId}-{suffix}). Provisioner auto-fills a short timestamp when not overridden to avoid "already exists".
    DBInstanceClass:
      Type: String
      Default: db.t3.micro
      AllowedValues: [db.t3.micro, db.t3.small, db.t3.medium, db.t3.large]
      Description: RDS instance class
    DBAllocatedStorage:
      Type: Number
      Default: 20
      MinValue: 20
      MaxValue: 1000
      Description: Database storage in GB
    LambdaMemorySize:
      Type: Number
      Default: 256
      AllowedValues: [128, 256, 512, 1024, 2048]
      Description: Lambda memory in MB
    LambdaTimeout:
      Type: Number
      Default: 30
      MinValue: 3
      MaxValue: 900
      Description: Lambda timeout in seconds
    AutoScalingMinSize:
      Type: Number
      Default: 1
      Description: Minimum instances in ASG
    AutoScalingMaxSize:
      Type: Number
      Default: 3
      Description: Maximum instances in ASG
    AutoScalingDesiredCapacity:
      Type: Number
      Default: 1
      Description: Desired instances in ASG
Only include parameters relevant to the requested architecture. Do not include RDS parameters if no database is requested. Do not include ASG parameters if no auto scaling is requested.

AMI PATHS:
Use ONLY /aws/service/ami-amazon-linux-latest/ prefix.
Valid: al2023-ami-kernel-6.1-x86_64, al2023-ami-kernel-6.1-arm64
NEVER use /aws/service/ami-amazon-linux-2023/
Declare as Parameter with Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id> and Default value.

NAMING:
(1) NEVER hardcode resource names — let CloudFormation auto-generate to avoid conflicts on stack updates and replacements
(2) If a name IS required: for S3 BucketName, NEVER use AWS::StackName — stack names often exceed 63 chars. Use !Sub 'app-${AWS::AccountId}' or omit BucketName so CloudFormation assigns a valid name. For other resources, !Sub '${AWS::StackName}-purpose' is OK if the result is short enough.
(3) RDS DBInstanceIdentifier: must be UNIQUE in the region. Use !Sub 'appDB-${DBInstanceIdentifierSuffix}' with Parameter DBInstanceIdentifierSuffix (default "appdb"). The provisioner auto-injects a short unique suffix when not overridden, so identifier stays unique and under 63 chars. Never use a bare literal only.
(4) Stack names used in resource names can cause length overflow. Keep ALL resource names that have length limits under 32 characters where AWS enforces it (ALB, Target Group, etc.). Exceptions — NEVER use stack name, use short literal or omit: DBInstanceIdentifier (max 63), S3 BucketName (3–63), ALB Name (max 32), Target Group Name (max 32). For any Name/Identifier with a 32-char limit, omit the property or use a short literal like "app-alb", "app-tg".

NETWORKING / VPC (ALWAYS USE EXISTING VPC):
(1) Never create VPC, Subnets, InternetGateway, VPCGatewayAttachment, NATGateway, EIP, RouteTable, Route, or SubnetRouteTableAssociation. Always use an existing VPC via parameters (deployer can pass default VPC).
(2) Add these Parameters: VpcId (Type: AWS::EC2::VPC::Id, Description: "Existing VPC ID (e.g. default VPC)"), PublicSubnetIds (Type: List<AWS::EC2::Subnet::Id>, Description: "At least 2 subnet IDs for ALB"), PrivateSubnetIds (Type: List<AWS::EC2::Subnet::Id>, Description: "At least 2 subnet IDs for ASG and RDS; for default VPC use same as PublicSubnetIds").
(3) All SecurityGroups: VpcId: !Ref VpcId. ALB Subnets: !Ref PublicSubnetIds. ASG VPCZoneIdentifier: !Ref PrivateSubnetIds. DBSubnetGroup SubnetIds: !Ref PrivateSubnetIds.
(4) Deployer passes VPC ID and subnet IDs at stack create/update (e.g. default VPC from aws ec2 describe-vpcs --filters Name=is-default,Values=true). No new VPC is ever created by the template.

SECURITY GROUPS:
(1) Always include both ingress and egress rules
(2) Use Ref to reference security groups in the same template — never hardcode sg- IDs
(3) For self-referencing security groups, use SourceSecurityGroupId with Ref
(4) Default egress should allow all outbound: CidrIp 0.0.0.0/0, IpProtocol -1
(5) NEVER use an empty SecurityGroupIngress or SecurityGroupEgress list — omit the property entirely if no rules
(6) For ALB security groups: allow inbound 80 and 443 from 0.0.0.0/0
(7) For app security groups: allow inbound only from ALB security group
(8) For DB security groups: allow inbound only from app security group on the database port

EC2 / AUTO SCALING:
(1) Do NOT include KeyName unless explicitly requested — it requires a pre-existing key pair
(2) Use LaunchTemplate (not LaunchConfiguration — it is deprecated)
(3) Auto Scaling Group needs MinSize, MaxSize, DesiredCapacity — all parameterized with defaults
(4) ASG must reference subnets via VPCZoneIdentifier (list of subnet IDs)
(5) ALB requires at least 2 subnets in different AZs
(6) ALB Name (Load Balancer) and Target Group Name: BOTH max 32 characters. Omit Name on both resources so CloudFormation auto-generates, or use short literals (e.g. "app-alb", "app-tg"). NEVER use !Sub with AWS::StackName for ALB or Target Group — causes CREATE_FAILED.
(7) ALB Target Group health check: use proper path (default /), healthy threshold, interval
(8) For ASG with ALB, use TargetGroupARNs (not LoadBalancerNames)
(9) Do NOT use CreationPolicy on ASG that requires SUCCESS signals (e.g. MinSuccessfulInstancesPercent, WaitOnResourceSignals) unless UserData explicitly runs cfn-signal when the instance is ready. Otherwise you get "Received 0 SUCCESS signal(s) out of 2. Unable to satisfy 100% MinSuccessfulInstancesPercent" and CREATE_FAILED. Prefer omitting CreationPolicy/UpdatePolicy on ASG so the stack completes when the ASG is created; instances can still launch and register with the ALB.
(10) For AWS::AutoScaling::ScalingPolicy with PolicyType TargetTrackingScaling: TargetTrackingConfiguration may only contain TargetValue, DisableScaleIn, PredefinedMetricSpecification, CustomizedMetricSpecification. Do NOT put ScaleInCooldown or ScaleOutCooldown inside TargetTrackingConfiguration — they are not permitted. Use Cooldown or EstimatedInstanceWarmup at the policy resource level if needed.
(11) UserData must be Base64 encoded using Fn::Base64
(12) AWS::EC2::LaunchTemplate: TagSpecifications at the resource level (same level as LaunchTemplateData) apply to the launch template itself — use ResourceType: "launch-template" ONLY there. Do NOT use ResourceType: "instance" at the LaunchTemplate resource level or you get "'instance' is not a valid taggable resource type". To tag instances/volumes when instances are launched, put TagSpecifications inside LaunchTemplateData with ResourceType: "instance" or "volume".

RDS:
(1) Engine: postgres, EngineVersion: '16' ONLY (use major version "16" so RDS selects the default available minor; do not pin to "16.3" — it can be deprecated or unavailable and causes "Cannot find version 16.3"). No MySQL, no Aurora, no other versions.
(2) DBInstanceIdentifier: set to !Sub 'appDB-${DBInstanceIdentifierSuffix}' with Parameter DBInstanceIdentifierSuffix (default "appdb"). Provisioner auto-injects a short unique suffix when not overridden — keeps identifier unique and under 63 chars. Never use bare literal only. Never use AWS::StackName (exceeds 63 chars).
(3) MasterUsername: 'dbadmin' (NEVER 'admin' — it is reserved for some engines)
(4) PREFER Secrets Manager pattern or ManageMasterUserPassword: true — if using password parameter it MUST have a default
(5) AllocatedStorage: parameterized, default 20, minimum 20 for gp3
(6) DBSubnetGroup: REQUIRED for VPC deployment, needs subnets in at least 2 AZs. For AWS::RDS::DBInstance use VPCSecurityGroups (exact property name — not VpcSecurityGroupIds); list of !Ref to security group resources.
(7) MultiAZ: true for production, false for dev (use Condition based on Environment parameter)
(8) DeletionPolicy: Snapshot (so data is preserved on stack deletion)
(9) BackupRetentionPeriod: at least 7
(10) StorageType: gp3 (not gp2). When AllocatedStorage is less than 400 GB, do NOT set Iops or StorageThroughput on the DB instance — AWS returns "You can't specify IOPS or storage throughput for engine postgres and a storage size less than 400." Omit Iops and StorageThroughput for typical dev sizes (e.g. 20–100 GB).
(11) DBInstanceClass: parameterized, default db.t3.micro
(12) PubliclyAccessible: false (always in private subnet)
(13) StorageEncrypted: true

LAMBDA:
(1) Runtime: python3.12 or nodejs20.x ONLY — no deprecated runtimes
(2) For simple functions, use inline Code with ZipFile — do NOT reference S3 buckets that may not exist
(3) Always include a Lambda execution role with basic logging permissions (logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents)
(4) Handler format: for Python use index.handler (with ZipFile), for Node.js use index.handler
(5) Timeout: parameterized, default 30 (default 3s is usually too short)
(6) MemorySize: parameterized, default 256
(7) FunctionName: max 64 characters. NEVER use !Sub with AWS::StackName in FunctionName — stack names are often long and cause "Member must have length less than or equal to 64". Use a short literal (e.g. "processor-fn", "BackgroundProcessor", "api-handler") or omit FunctionName so CloudFormation assigns a unique name.
(8) For Lambda in VPC: needs security group, private subnets, and NAT Gateway for internet access

API GATEWAY:
(1) For REST API: AWS::ApiGateway::Deployment MUST have DependsOn on ALL Method resources
(2) For HTTP API: use AWS::ApiGatewayV2::Api with ProtocolType: HTTP
(3) Always include a Stage resource
(4) AWS::ApiGateway::Stage: do NOT put LoggingLevel or DataTraceEnabled at the Stage Properties root — they are not permitted. Use MethodSettings (list of MethodSetting) with ResourcePath "*" and HttpMethod "*" if you need logging/tracing.
(5) Lambda permission (AWS::Lambda::Permission) required for API Gateway to invoke Lambda — SourceArn must match the API
(6) Use AWS::ApiGateway::RestApi for REST, AWS::ApiGatewayV2::Api for HTTP/WebSocket
(7) Include CORS configuration if the API will be called from browsers

S3:
(1) BucketName must be 3–63 characters and globally unique. To avoid "already exists" on redeploy or multiple stacks, use a Parameter BucketNameSuffix (Type: String, Default: "files" or empty). Set BucketName to !Sub 'app-${AWS::AccountId}-${BucketNameSuffix}'. The provisioner auto-injects a short timestamp suffix when not overridden, so names are unique (e.g. app-123456789012-12345678). Omit BucketName only if you do not need a predictable name.
(2) If you specify BucketName without a suffix param: use !Sub 'app-${AWS::AccountId}-${BucketNameSuffix}' and add Parameter BucketNameSuffix. NEVER use only 'app-${AWS::AccountId}' or 'app-files-${AWS::AccountId}' — that name can already exist. NEVER use AWS::StackName in BucketName — exceeds 63 chars.
(3) For static website hosting, include WebsiteConfiguration
(4) DeletionPolicy: Retain for important data buckets
(5) Enable versioning for data buckets
(6) Block public access unless explicitly needed for static hosting

CLOUDFRONT:
(1) AWS::CloudFront::Distribution has two top-level Properties: DistributionConfig (required) and Tags (optional). Do NOT put Tags inside DistributionConfig — "extraneous key [Tags] is not permitted" there; put Tags as a sibling of DistributionConfig.

DYNAMODB:
(1) BillingMode: PAY_PER_REQUEST for dev (no capacity planning needed), PROVISIONED for production
(2) Always define KeySchema and AttributeDefinitions
(3) PointInTimeRecoverySpecification: PointInTimeRecoveryEnabled: true
(4) SSESpecification: SSEEnabled: true

IAM:
(1) Use least-privilege policies
(2) Always use AssumeRolePolicyDocument with correct service principal
(3) Lambda principal: lambda.amazonaws.com
(4) EC2 principal: ec2.amazonaws.com
(5) For EC2 instances, create InstanceProfile that references the Role
(6) NEVER use wildcard Resource: '*' with dangerous actions — scope to specific ARNs where possible
(7) Use managed policies where appropriate (e.g. AmazonSSMManagedInstanceCore for EC2)
(8) When granting access to a Secrets Manager secret in an IAM policy, use !Ref SecretResource for the Resource ARN — never !GetAtt SecretResource.Arn (invalid).

DEPENDENCIES (explicit DependsOn required):
(1) NAT Gateway → DependsOn: VPCGatewayAttachment
(2) EIP for NAT → DependsOn: VPCGatewayAttachment
(3) Any route to IGW → DependsOn: VPCGatewayAttachment
(4) API Gateway Deployment → DependsOn: all API Gateway Method resources
(5) RDS Instance → needs DBSubnetGroup (implicit via Ref, but add explicit if needed)
(6) Lambda with VPC → needs VPC security group and subnets, and a NAT Gateway for internet access
(7) Any resource that uses an EIP → DependsOn: VPCGatewayAttachment

OUTPUTS:
(1) Always include useful outputs: URLs, ARNs, resource IDs, connection strings
(2) Use Fn::GetAtt for ARNs and DNS names where supported. For AWS::SecretsManager::Secret use !Ref (not GetAtt) to get the ARN — GetAtt Secret.Arn is invalid.
(3) Export outputs that other stacks might need
(4) For ALB: output the DNS name
(5) For API Gateway: output the invoke URL
(6) For RDS: output the endpoint address and port
(7) For S3: output the bucket name and ARN
(8) For Lambda: output the function ARN
(9) For VPC: output VPC ID and subnet IDs

TAGS:
Every taggable resource must include:
  - Key: stack-creator, Value: aws-architect-mcp
  - Key: project, Value: mwc-demo
  - Key: environment, Value: !Ref Environment

NEVER DO:
- Leave ANY parameter without a Default value
- Leave password parameters without a default or Secrets Manager
- Hardcode AZ names like us-east-1a — use Fn::GetAZs
- Hardcode account IDs — use AWS::AccountId
- Hardcode region names — use AWS::Region
- Reference resources not defined in this template
- Use !GetAtt on AWS::SecretsManager::Secret for Arn — use !Ref SecretResource to get the ARN instead
- Use deprecated types (LaunchConfiguration, python3.8, nodejs16.x, etc.)
- Create ALB with subnets in only one AZ
- Create RDS without DBSubnetGroup in a VPC
- Use VpcSecurityGroupIds on AWS::RDS::DBInstance — use VPCSecurityGroups (exact CloudFormation property name)
- Set RDS DBInstanceIdentifier to a bare literal only — use !Sub 'appDB-${DBInstanceIdentifierSuffix}' (default "appdb"; provisioner auto-injects unique short suffix). Do not use AWS::StackName (exceeds 63 chars).
- Set S3 BucketName using AWS::StackName — BucketName must be 3–63 chars. Use !Sub 'app-${AWS::AccountId}-${BucketNameSuffix}' with BucketNameSuffix param (provisioner injects timestamp); or omit BucketName
- Set ALB Name (AWS::ElasticLoadBalancingV2::LoadBalancer) or Target Group Name (AWS::ElasticLoadBalancingV2::TargetGroup) using AWS::StackName or any value longer than 32 chars — omit Name or use short literal ("app-alb", "app-tg"). Keep all ELBv2 names under 32 characters.
- Create NAT Gateway without DependsOn VPCGatewayAttachment
- Use 'admin' as RDS MasterUsername
- Use empty SecurityGroupIngress or SecurityGroupEgress arrays
- Leave Lambda without an execution role
- Use AWS::StackName in Lambda FunctionName — max 64 chars; use short literal or omit FunctionName
- Reference S3 objects for Lambda code — use inline ZipFile
- Create a security group rule referencing a group not in this template
- Use gp2 storage for RDS — use gp3
- Set Iops or StorageThroughput on RDS when AllocatedStorage < 400 GB — not allowed for postgres; omit both for storage under 400 GB
- Set RDS PostgreSQL EngineVersion to "16.3" or any specific minor — use "16" (major only) so RDS picks the default available minor; 16.3 may not exist and causes "Cannot find version 16.3"
- Create resources with PubliclyAccessible: true unless explicitly requested
- Forget to add Lambda Permission for API Gateway integration
- Forget DependsOn for API Gateway Deployment on Method resources
- Put ScaleInCooldown or ScaleOutCooldown inside TargetTrackingConfiguration of AWS::AutoScaling::ScalingPolicy — not permitted; use Cooldown or EstimatedInstanceWarmup at policy level only
- Put LoggingLevel or DataTraceEnabled at AWS::ApiGateway::Stage Properties root — not permitted; use MethodSettings with a MethodSetting entry (ResourcePath "*", HttpMethod "*") for logging/tracing
- Put Tags inside DistributionConfig of AWS::CloudFront::Distribution — not permitted; Tags must be a top-level property of the resource (sibling to DistributionConfig)
- Use ASG CreationPolicy that requires resource signals (MinSuccessfulInstancesPercent, WaitOnResourceSignals) without UserData that runs cfn-signal — causes "Received 0 SUCCESS signal(s)" and CREATE_FAILED; omit CreationPolicy on ASG instead
- For AWS::EC2::LaunchTemplate do NOT use TagSpecifications at resource level with ResourceType "instance" — causes "'instance' is not a valid taggable resource type"; use ResourceType "launch-template" for tags on the launch template; put instance/volume tags inside LaunchTemplateData.TagSpecifications
- Use No export named ImportValue references — keep everything in one template
- No Cognito user pool — do not use AWS::Cognito::UserPool, UserPoolClient, or any Cognito resources
- Create VPC/Subnet/IGW/NAT/Route resources — always use Parameters VpcId, PublicSubnetIds, PrivateSubnetIds (deployer passes existing/default VPC)

ONE-SHOT EXAMPLE (follow this pattern — existing VPC params, no VPC/Subnet/IGW in Resources, single RDS postgres with DBInstanceIdentifierSuffix):
---
AWSTemplateFormatVersion: '2010-09-09'
Description: Three-tier app with ALB, ASG, RDS — uses existing VPC
Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, staging, prod]
  InstanceType:
    Type: String
    Default: t3.micro
  LatestAmiId:
    Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
    Default: /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64
  VpcId:
    Type: AWS::EC2::VPC::Id
    Description: Existing VPC ID
  PublicSubnetIds:
    Type: List<AWS::EC2::Subnet::Id>
    Description: At least 2 subnet IDs for ALB
  PrivateSubnetIds:
    Type: List<AWS::EC2::Subnet::Id>
    Description: At least 2 subnet IDs for ASG and RDS
  DBInstanceIdentifierSuffix:
    Type: String
    Default: appdb
    Description: Suffix for RDS identifier (provisioner auto-fills unique value)
  DBInstanceClass:
    Type: String
    Default: db.t3.micro
Resources:
  DBSecret:
    Type: AWS::SecretsManager::Secret
    Properties:
      Name: !Sub '${AWS::StackName}-db-secret'
      GenerateSecretString:
        SecretStringTemplate: '{"username": "dbadmin"}'
        GenerateStringKey: password
        PasswordLength: 24
        ExcludeCharacters: '"@/\\'
      Tags:
        - Key: stack-creator
          Value: aws-architect-mcp
        - Key: project
          Value: mwc-demo
  ALBSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: ALB SG
      VpcId: !Ref VpcId
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
      SecurityGroupEgress:
        - IpProtocol: -1
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Name
          Value: app-alb-sg
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: App SG
      VpcId: !Ref VpcId
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 8080
          ToPort: 8080
          SourceSecurityGroupId: !Ref ALBSecurityGroup
      SecurityGroupEgress:
        - IpProtocol: -1
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Name
          Value: app-sg
  DatabaseSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: DB SG
      VpcId: !Ref VpcId
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 5432
          ToPort: 5432
          SourceSecurityGroupId: !Ref AppSecurityGroup
      SecurityGroupEgress:
        - IpProtocol: -1
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Name
          Value: app-db-sg
  DBSubnetGroup:
    Type: AWS::RDS::DBSubnetGroup
    Properties:
      DBSubnetGroupDescription: Subnets for RDS
      SubnetIds: !Ref PrivateSubnetIds
      Tags:
        - Key: Name
          Value: app-db-subnets
  AppDB:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    Properties:
      DBInstanceIdentifier: !Sub 'appDB-${DBInstanceIdentifierSuffix}'
      Engine: postgres
      EngineVersion: '16'
      MasterUsername: dbadmin
      MasterUserPassword: !Sub '{{resolve:secretsmanager:${DBSecret}:SecretString:password}}'
      DBSubnetGroupName: !Ref DBSubnetGroup
      VPCSecurityGroups:
        - !Ref DatabaseSecurityGroup
      AllocatedStorage: 20
      DBInstanceClass: !Ref DBInstanceClass
      StorageType: gp3
      StorageEncrypted: true
      BackupRetentionPeriod: 7
      PubliclyAccessible: false
      Tags:
        - Key: stack-creator
          Value: aws-architect-mcp
        - Key: project
          Value: mwc-demo
  ApplicationLoadBalancer:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Type: application
      Scheme: internet-facing
      Subnets: !Ref PublicSubnetIds
      SecurityGroups:
        - !Ref ALBSecurityGroup
      Tags:
        - Key: Name
          Value: app-alb
  TargetGroup:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      Port: 8080
      Protocol: HTTP
      VpcId: !Ref VpcId
      HealthCheckPath: /
      HealthCheckProtocol: HTTP
      Tags:
        - Key: Name
          Value: app-tg
Outputs:
  LoadBalancerDNS:
    Value: !GetAtt ApplicationLoadBalancer.DNSName
  DBEndpoint:
    Value: !GetAtt AppDB.Endpoint.Address
---
"""
        # Inject official schema hints for key resource types so the model uses exact property names (reduces deploy failures)
        try:
            schema_parts = [_schema_summary_for_builder(rt) for rt in _KEY_SCHEMA_TYPES_FOR_BUILDER]
            if schema_parts:
                system_prompt += "\n\nOFFICIAL SCHEMA HINTS (use exact property names and required fields where applicable):\n" + "\n".join(schema_parts)
        except Exception:
            pass
        user_message = f"""Generate a CloudFormation template for: {prompt}

Format: {format.upper()}. Verify every Ref and GetAtt points to a defined resource. Return ONLY the template."""
        t_bedrock = time.time()
        # CRITICAL: enable_thinking=False for speed. With thinking this tool takes 60-70s; without, ~15-35s.
        response = converse_with_retry(
            bedrock, BEDROCK_MODEL_ID, system_prompt, user_message, max_tokens=25000, enable_thinking=False,
            system_cache_ttl="1h"
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
        
        # If auto_fix is disabled, just return the error (with violations shape for consistency with compliance tools)
        if not auto_fix:
            return {
                'success': False,
                'valid': False,
                'error': error_message,
                'violations': [{
                    'rule_id': 'TemplateValidation',
                    'severity': 'ERROR',
                    'resource': '',
                    'resource_type': '',
                    'message': error_message,
                    'remediation': 'Run with auto_fix=true to attempt automatic fix, or correct the template manually.',
                }],
            }
        
        # Optionally fetch official schema for resource type mentioned in error (reduces deploy failures)
        schema_hint = ""
        match = re.search(r"AWS::[A-Za-z0-9]+::[A-Za-z0-9]+", error_message)
        if match:
            rtype = match.group(0)
            schema_result = get_resource_schema_information(rtype)
            if schema_result.get("success") and schema_result.get("schema"):
                schema_hint = f"\n\nOfficial CloudFormation schema for {rtype} (use exact property names and types):\n{json.dumps(schema_result['schema'], indent=2)[:12000]}"
        
        # Auto-fix: Use Claude to fix the template
        try:
            bedrock = get_bedrock_client()
            
            system_prompt = """CloudFormation expert. Fix validation errors.

Rules:
1. Check all resource references (Ref, GetAtt, DependsOn)
2. Ensure referenced resources exist
3. Fix resource names and dependencies
4. When touching RDS (AWS::RDS::DBInstance): for PostgreSQL use EngineVersion "16" (major only) so RDS picks the default minor; do not use "16.3" as it may not exist in all regions. Avoid deprecated versions.
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
- For RDS PostgreSQL: Use EngineVersion "16" (major version only), not "16.3" — minor versions can be deprecated; "16" lets RDS choose the available default.

Return ONLY the corrected template.""" + schema_hint

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
                    'template': fixed_template,
                    'violations': [{
                        'rule_id': 'TemplateValidation',
                        'severity': 'ERROR',
                        'resource': '',
                        'resource_type': '',
                        'message': str(revalidation_error),
                        'remediation': 'Review the fixed template and correct remaining errors, or try validate_cfn_template again with the updated template.',
                    }],
                }
                
        except Exception as fix_error:
            return {
                'success': False,
                'valid': False,
                'error': f'Validation failed: {error_message}. Auto-fix failed: {str(fix_error)}',
                'violations': [{
                    'rule_id': 'TemplateValidation',
                    'severity': 'ERROR',
                    'resource': '',
                    'resource_type': '',
                    'message': error_message,
                    'remediation': 'Auto-fix failed. Correct the template manually or retry.',
                }],
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
                   If the template has VpcId, PublicSubnetIds, or PrivateSubnetIds and you omit them,
                   the default VPC and its subnets are filled in automatically (no need to pass them).
    """
    if READONLY_MODE:
        return {
            "success": False,
            "error": "Server is in read-only mode. Provisioning is disabled. Set MCP_READONLY=false to allow stack create/update.",
        }
    # Use a short stack name when the provided one is too long (avoids Lambda/other resource names exceeding 64 chars when template uses !Sub '${AWS::StackName}-...')
    _stack_name = (stack_name or '').strip()
    if len(_stack_name) > 50:
        _stack_name = "AgenticArchitect-" + str(int(time.time()))[-8:]
    stack_name = _stack_name
    # Reject templates that create VPC/Subnet/IGW/NAT (account limits; we use existing VPC only)
    _FORBIDDEN_RESOURCE_TYPES = {
        'AWS::EC2::VPC', 'AWS::EC2::Subnet', 'AWS::EC2::InternetGateway',
        'AWS::EC2::VPCGatewayAttachment', 'AWS::EC2::NATGateway', 'AWS::EC2::EIP',
        'AWS::EC2::RouteTable', 'AWS::EC2::Route', 'AWS::EC2::SubnetRouteTableAssociation',
    }
    try:
        if template_body.strip().startswith('{'):
            doc = json.loads(template_body)
        else:
            doc = yaml.safe_load(template_body)
        resources = doc.get('Resources') or {}
        found = [r for r, defn in resources.items() if isinstance(defn, dict) and defn.get('Type') in _FORBIDDEN_RESOURCE_TYPES]
        if found:
            types = list({resources[r].get('Type') for r in found if isinstance(resources.get(r), dict)})
            return {
                'success': False,
                'error': f'Template must not create VPC resources (account limit). Found: {", ".join(types)}. Rebuild the template using Parameters VpcId, PublicSubnetIds, PrivateSubnetIds and references like !Ref VpcId (no AWS::EC2::VPC, Subnet, InternetGateway, NAT, Route).',
            }
    except Exception:
        pass  # parse failed; let CloudFormation validate later
    # Strip invalid keys that cause "extraneous key not permitted" (e.g. ScaleInCooldown/ScaleOutCooldown inside TargetTrackingConfiguration)
    template_body = _normalize_cfn_template_for_provision(template_body)
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

        # Build parameter list: user-provided + auto-fill default VPC/subnets (never send literal "default" to CloudFormation)
        user_params = {}
        if parameters:
            for p in parameters:
                if p.get('ParameterKey'):
                    user_params[p['ParameterKey']] = str(p.get('ParameterValue', ''))
        template_param_keys = set()
        try:
            if template_body.strip().startswith('{'):
                template_param_keys = set(json.loads(template_body).get('Parameters', {}).keys())
            else:
                template_param_keys = set(yaml.safe_load(template_body).get('Parameters', {}).keys())
        except Exception:
            pass
        # Keys that must never be sent as literal "default" (match case-insensitively)
        VPC_PARAM_KEYS = ('VpcId', 'PublicSubnetIds', 'PrivateSubnetIds')
        def _is_vpc_param_key(key):
            return (key or '').strip().lower() in ('vpcid', 'publicsubnetids', 'privatesubnetids')
        def _use_default_vpc_value(key):
            val = (user_params.get(key) or '').strip().lower()
            return not val or val == 'default'
        # Check if we need to resolve VPC: template has these params (parsed or detected in body) or client sent them
        template_has_vpc_params = any(k for k in template_param_keys if _is_vpc_param_key(k))
        if not template_has_vpc_params and 'Parameters' in template_body:
            # Fallback when parse failed: detect VPC params from template string so we still fill them
            for name in ('VpcId', 'PublicSubnetIds', 'PrivateSubnetIds'):
                if name in template_body:
                    template_has_vpc_params = True
                    break
        need_vpc = template_has_vpc_params or any(
            _is_vpc_param_key(k) and _use_default_vpc_value(k) for k in user_params
        )
        if need_vpc:
            default_subnet_ids = _get_subnet_ids_for_vpc(HARDCODED_DEFAULT_VPC_ID)
            if default_subnet_ids:
                default_vpc_id = HARDCODED_DEFAULT_VPC_ID
            else:
                default_vpc_id, default_subnet_ids = _get_default_vpc_and_subnets()
            if default_vpc_id and default_subnet_ids:
                subnet_val = ','.join(default_subnet_ids)
                for key in list(user_params.keys()):
                    if not _is_vpc_param_key(key):
                        continue
                    if not _use_default_vpc_value(key):
                        continue
                    if key.strip().lower() == 'vpcid':
                        user_params[key] = default_vpc_id
                    else:
                        user_params[key] = subnet_val
                # Set canonical keys so required params are present (from parsed keys or fallback)
                for ckey in VPC_PARAM_KEYS:
                    if (ckey in template_param_keys or not template_param_keys) and _use_default_vpc_value(ckey):
                        if ckey == 'VpcId':
                            user_params[ckey] = default_vpc_id
                        else:
                            user_params[ckey] = subnet_val
                # When parse failed, ensure we still send all three so CFN doesn't say "must have values"
                if not template_param_keys:
                    user_params['VpcId'] = default_vpc_id
                    user_params['PublicSubnetIds'] = subnet_val
                    user_params['PrivateSubnetIds'] = subnet_val
            for key in list(user_params.keys()):
                if _is_vpc_param_key(key) and _use_default_vpc_value(key):
                    return {
                        'success': False,
                        'error': f'Could not resolve default VPC/subnets for {key}. Ensure vpc-0ca2fc76 exists in this region and has subnets, or pass explicit parameter values.',
                    }
        # Auto-inject short unique suffixes on create (timestamp last 8 digits) to avoid "already exists"
        unique_suffix = str(int(time.time()))[-8:]
        if not stack_exists:
            def _is_db_suffix_key(k):
                return (k or '').strip().lower() == 'dbinstanceidentifiersuffix'
            _db_suffix_key = next((k for k in template_param_keys if _is_db_suffix_key(k)), None)
            template_has_db_suffix = _db_suffix_key is not None or 'DBInstanceIdentifierSuffix' in template_body or 'dbinstanceidentifiersuffix' in template_body.lower()
            if template_has_db_suffix:
                current = (user_params.get(_db_suffix_key or 'DBInstanceIdentifierSuffix') or '').strip().lower()
                if not current or current == 'appdb':
                    key_to_set = _db_suffix_key or 'DBInstanceIdentifierSuffix'
                    user_params[key_to_set] = unique_suffix
            # S3: inject BucketNameSuffix so bucket name is unique (avoids "app-files-{AccountId} already exists")
            def _is_bucket_suffix_key(k):
                return (k or '').strip().lower() == 'bucketnamesuffix'
            _bucket_suffix_key = next((k for k in template_param_keys if _is_bucket_suffix_key(k)), None)
            template_has_bucket_suffix = _bucket_suffix_key is not None or 'BucketNameSuffix' in template_body or 'bucketnamesuffix' in template_body.lower()
            if template_has_bucket_suffix:
                current = (user_params.get(_bucket_suffix_key or 'BucketNameSuffix') or '').strip().lower()
                if not current or current in ('files', 'data', 'bucket'):
                    key_to_set = _bucket_suffix_key or 'BucketNameSuffix'
                    user_params[key_to_set] = unique_suffix
        # Final safeguard: never send literal "default" for VPC params to CloudFormation
        if user_params:
            params['Parameters'] = []
            for k, v in user_params.items():
                if _is_vpc_param_key(k) and (v or '').strip().lower() == 'default':
                    continue
                params['Parameters'].append({'ParameterKey': k, 'ParameterValue': v})

        if stack_exists:
            response = cfn.update_stack(**params)
            action = 'updated'
        else:
            response = cfn.create_stack(**params)
            action = 'created'

        result = {
            'success': True,
            'action': action,
            'stack_id': response['StackId'],
        }
        if stack_name:
            result['stack_name'] = stack_name
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }


@mcp.tool()
def delete_cfn_stack(stack_name: str) -> dict:
    """Delete a CloudFormation stack by name."""
    if READONLY_MODE:
        return {
            "success": False,
            "error": "Server is in read-only mode. Deletion is disabled. Set MCP_READONLY=false to allow.",
        }
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
