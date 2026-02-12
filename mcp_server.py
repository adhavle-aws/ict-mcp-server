# mcp_server.py
from mcp.server.fastmcp import FastMCP
from typing import Optional
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

# Cross-account provision: MCP runs in 611291728384 but creates stacks in another account.
# Set CFN_TARGET_ACCOUNT_ID and CFN_TARGET_ROLE_NAME (e.g. 471112858498, AgentCoreProvisionRole)
# or CFN_TARGET_ROLE_ARN (full ARN). Then get_cfn_client/get_ec2_client use assumed role for that account.
CFN_TARGET_ACCOUNT_ID = os.environ.get('CFN_TARGET_ACCOUNT_ID', '').strip() or None
CFN_TARGET_ROLE_NAME = os.environ.get('CFN_TARGET_ROLE_NAME', '').strip() or None
CFN_TARGET_ROLE_ARN = os.environ.get('CFN_TARGET_ROLE_ARN', '').strip() or None
_assumed_creds_cache = None
_assumed_creds_expiry = 0
ASSUMED_CREDS_TTL_SEC = 300  # 5 minutes


def _get_cross_account_role_arn():
    """Return role ARN for target account if cross-account provision is configured."""
    if CFN_TARGET_ROLE_ARN:
        return CFN_TARGET_ROLE_ARN
    if CFN_TARGET_ACCOUNT_ID and CFN_TARGET_ROLE_NAME:
        return f"arn:aws:iam::{CFN_TARGET_ACCOUNT_ID}:role/{CFN_TARGET_ROLE_NAME}"
    return None


def _get_cross_account_credentials(region=None):
    """Assume role in target account; return dict with AccessKeyId, SecretAccessKey, SessionToken, or None."""
    role_arn = _get_cross_account_role_arn()
    if not role_arn:
        return None
    global _assumed_creds_cache, _assumed_creds_expiry
    now = time.time()
    if _assumed_creds_cache is not None and now < _assumed_creds_expiry:
        return _assumed_creds_cache
    try:
        sts = boto3.client('sts', region_name=region or os.environ.get('AWS_REGION', 'us-east-1'))
        resp = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='AgentCoreCfnProvision',
            DurationSeconds=3600,
        )
        creds = resp['Credentials']
        _assumed_creds_cache = {
            'AccessKeyId': creds['AccessKeyId'],
            'SecretAccessKey': creds['SecretAccessKey'],
            'SessionToken': creds['SessionToken'],
        }
        _assumed_creds_expiry = now + ASSUMED_CREDS_TTL_SEC
        return _assumed_creds_cache
    except Exception:
        _assumed_creds_cache = None
        _assumed_creds_expiry = 0
        return None


def get_cfn_client(region=None):
    """Get CloudFormation client; uses target account via AssumeRole when CFN_TARGET_* env is set."""
    region = region or os.environ.get('AWS_REGION', 'us-east-1')
    creds = _get_cross_account_credentials(region=region)
    if creds:
        return boto3.client(
            'cloudformation',
            region_name=region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )
    return boto3.client('cloudformation', region_name=region)


def get_ec2_client(region=None):
    """Get EC2 client; uses target account via AssumeRole when CFN_TARGET_* env is set (for VPC/subnet resolution)."""
    region = region or os.environ.get('AWS_REGION', 'us-east-1')
    creds = _get_cross_account_credentials(region=region)
    if creds:
        return boto3.client(
            'ec2',
            region_name=region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )
    return boto3.client('ec2', region_name=region)


# Hardcoded VPC for demo when default VPC is not available (same-account only; vpc-0ca2fc76 was for 611291728384).
# When cross-account (CFN_TARGET_*), EC2 calls run in target account — use that account's default VPC or set CFN_TARGET_DEFAULT_VPC_ID.
HARDCODED_DEFAULT_VPC_ID = "vpc-0ca2fc76"
# Optional: fallback VPC for target account when it has no default VPC (e.g. CFN_TARGET_DEFAULT_VPC_ID=vpc-xxxxx in 471112858498).
CFN_TARGET_DEFAULT_VPC_ID = os.environ.get('CFN_TARGET_DEFAULT_VPC_ID', '').strip() or None


def _get_subnet_ids_for_vpc(vpc_id: str, region=None):
    """Return list of subnet IDs for the given VPC. Uses get_ec2_client() so respects cross-account (target account EC2)."""
    try:
        ec2 = get_ec2_client(region=region)
        subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]).get('Subnets', [])
        return [s['SubnetId'] for s in subnets]
    except Exception:
        return []


def _one_subnet_per_az(subnet_ids: list, region=None):
    """Return subnet IDs with at most one per AZ. ALB requires no two subnets in the same AZ."""
    if not subnet_ids:
        return []
    try:
        ec2 = get_ec2_client(region=region)
        resp = ec2.describe_subnets(SubnetIds=subnet_ids)
        by_az = {}
        for s in resp.get('Subnets', []):
            az = s.get('AvailabilityZone') or s.get('AvailabilityZoneId')
            if az and s.get('SubnetId') and az not in by_az:
                by_az[az] = s['SubnetId']
        return list(by_az.values())
    except Exception:
        return subnet_ids  # fallback to original list


def _get_default_vpc_and_subnets(region=None):
    """Return (vpc_id, list of subnet_ids) for the default VPC in the current EC2 account (runtime or assumed target).
    When CFN_TARGET_* is set, EC2 is the target account — so we get that account's default VPC.
    Fallback: CFN_TARGET_DEFAULT_VPC_ID (if set), else HARDCODED_DEFAULT_VPC_ID (only exists in source account)."""
    try:
        ec2 = get_ec2_client(region=region)
        vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}]).get('Vpcs', [])
        if vpcs:
            vpc_id = vpcs[0]['VpcId']
            subnet_ids = _get_subnet_ids_for_vpc(vpc_id, region=region)
            return vpc_id, subnet_ids
        # Fallback: target-account VPC if set, else hardcoded demo VPC (only works in account where that VPC exists)
        for fallback_vpc in (CFN_TARGET_DEFAULT_VPC_ID, HARDCODED_DEFAULT_VPC_ID):
            if not fallback_vpc:
                continue
            subnet_ids = _get_subnet_ids_for_vpc(fallback_vpc, region=region)
            if subnet_ids:
                return fallback_vpc, subnet_ids
        return None, []
    except Exception:
        return None, []


def _s3_bucket_name_uses_suffix(bucket_name_value) -> bool:
    """Return True if BucketName already references BucketNameSuffix (so provisioner can inject unique value)."""
    if bucket_name_value is None:
        return False
    s = json.dumps(bucket_name_value) if not isinstance(bucket_name_value, str) else bucket_name_value
    return 'bucketnamesuffix' in s.lower()


def _normalize_cfn_template_for_provision(template_body: str) -> str:
    """Strip invalid keys from template so provision succeeds (e.g. S3 BucketPolicy PolicyText -> PolicyDocument; ScalingPolicy EstimatedWarmupSeconds -> EstimatedInstanceWarmupSeconds; S3 BucketName uses BucketNameSuffix; ScaleInCooldown/ScaleOutCooldown inside TargetTrackingConfiguration; LoggingLevel/DataTraceEnabled at AWS::ApiGateway::Stage root; Tags inside CloudFront DistributionConfig)."""
    try:
        # String-level fallback: fix app-${AWS::AccountId}-<fixed> so provisioner can inject BucketNameSuffix (catches any structure parse might miss)
        if 'S3::Bucket' in template_body and 'BucketNameSuffix' not in template_body and '${BucketNameSuffix}' not in template_body:
            for suffix in ('media', 'files', 'content', 'data', 'bucket'):
                old = f'${{AWS::AccountId}}-{suffix}'
                if old in template_body:
                    template_body = template_body.replace(old, f'${{AWS::AccountId}}-${{BucketNameSuffix}}-{suffix}')
                    try:
                        is_j = template_body.strip().startswith('{')
                        doc = json.loads(template_body) if is_j else yaml.safe_load(template_body)
                        if isinstance(doc, dict):
                            params = doc.setdefault('Parameters', {})
                            if 'BucketNameSuffix' not in params:
                                params['BucketNameSuffix'] = {'Type': 'String', 'Default': ''}
                                template_body = json.dumps(doc, indent=2) if is_j else yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)
                    except Exception:
                        pass
                    break
        is_json = template_body.strip().startswith('{')
        if is_json:
            doc = json.loads(template_body)
            resources = doc.get('Resources') or {}
            params = doc.setdefault('Parameters', {})
            changed = False
            for logical_id, rdef in resources.items():
                if not isinstance(rdef, dict):
                    continue
                rtype = rdef.get('Type')
                props = rdef.get('Properties') or {}
                if rtype == 'AWS::AutoScaling::ScalingPolicy':
                    # CloudFormation uses EstimatedInstanceWarmupSeconds, not EstimatedWarmupSeconds (any casing)
                    for key in list(props):
                        if key.strip().lower().replace('_', '') == 'estimatedwarmupseconds':
                            props['EstimatedInstanceWarmupSeconds'] = props.pop(key)
                            changed = True
                            break
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
                    if isinstance(dist_cfg, dict):
                        if 'Tags' in dist_cfg:
                            tags = dist_cfg.pop('Tags')
                            if tags is not None and 'Tags' not in props:
                                props['Tags'] = tags
                            changed = True
                        if 'ViewerProtocolPolicy' in dist_cfg:
                            del dist_cfg['ViewerProtocolPolicy']
                            changed = True
                        default_beh = dist_cfg.get('DefaultCacheBehavior')
                        if isinstance(default_beh, dict):
                            if 'OriginId' in default_beh and 'TargetOriginId' not in default_beh:
                                default_beh['TargetOriginId'] = default_beh.pop('OriginId')
                                changed = True
                            elif 'OriginId' in default_beh:
                                del default_beh['OriginId']
                                changed = True
                        for cb in dist_cfg.get('CacheBehaviors') or []:
                            if isinstance(cb, dict) and 'OriginId' in cb and 'TargetOriginId' not in cb:
                                cb['TargetOriginId'] = cb.pop('OriginId')
                                changed = True
                            elif isinstance(cb, dict) and 'OriginId' in cb:
                                del cb['OriginId']
                                changed = True
                elif rtype == 'AWS::EC2::Instance':
                    # CloudFormation uses Tags (list of Key/Value), not TagSpecifications; convert if present and always remove key
                    tag_specs = props.get('TagSpecifications')
                    if isinstance(tag_specs, list) and tag_specs:
                        for spec in tag_specs:
                            if isinstance(spec, dict) and 'Tags' in spec:
                                if 'Tags' not in props:
                                    props['Tags'] = spec['Tags']
                                break
                    if 'TagSpecifications' in props:
                        del props['TagSpecifications']
                        changed = True
                elif rtype == 'AWS::ApiGateway::Resource':
                    path_part = props.get('PathPart')
                    if isinstance(path_part, str):
                        part = path_part.strip()
                        if part.startswith('{') and part.endswith('}'):
                            inner = part[1:-1].strip().replace(' ', '').replace('-', '_')
                            if inner and inner != part[1:-1]:
                                props['PathPart'] = '{' + inner + '}'
                                changed = True
                        else:
                            allowed = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:')
                            fixed = ''.join(c if c in allowed else '_' for c in part)
                            if fixed != part:
                                props['PathPart'] = fixed
                                changed = True
                elif rtype == 'AWS::Logs::LogGroup':
                    log_name = props.get('LogGroupName')
                    if isinstance(log_name, str) and log_name.strip():
                        props['LogGroupName'] = {'Fn::Sub': '/app/${AWS::StackName}'}
                        changed = True
                elif rtype == 'AWS::S3::Bucket':
                    # Force unique bucket name via BucketNameSuffix (provisioner injects timestamp on create)
                    bucket_name = props.get('BucketName')
                    if bucket_name is None or not _s3_bucket_name_uses_suffix(bucket_name):
                        safe_id = logical_id.lower().replace('_', '-')[:40]
                        props['BucketName'] = {'Fn::Sub': f'app-${{AWS::AccountId}}-${{BucketNameSuffix}}-{safe_id}'}
                        if 'BucketNameSuffix' not in params:
                            params['BucketNameSuffix'] = {'Type': 'String', 'Default': ''}
                        changed = True
                elif rtype == 'AWS::S3::BucketPolicy':
                    # CloudFormation uses PolicyDocument, not PolicyText
                    policy_text = props.pop('PolicyText', None)
                    if policy_text is not None and 'PolicyDocument' not in props:
                        if isinstance(policy_text, str):
                            try:
                                props['PolicyDocument'] = json.loads(policy_text)
                            except Exception:
                                props['PolicyDocument'] = policy_text
                        else:
                            props['PolicyDocument'] = policy_text
                        changed = True
                elif rtype == 'AWS::CloudFormation::Stack':
                    # Normalize nested stack inline template so ScalingPolicy etc. are fixed in child stacks
                    tb = props.get('TemplateBody')
                    if isinstance(tb, str) and tb.strip():
                        normalized = _normalize_cfn_template_for_provision(tb)
                        if normalized != tb:
                            props['TemplateBody'] = normalized
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
        result = '\n'.join(out) if changed else template_body
        # YAML: fix LogGroup, ScalingPolicy, S3 bucket suffix, nested stacks
        try:
            doc = yaml.safe_load(result)
            if isinstance(doc, dict):
                resources = doc.get('Resources') or {}
                params = doc.setdefault('Parameters', {})
                yaml_changed = False
                for logical_id, rdef in resources.items():
                    if not isinstance(rdef, dict):
                        continue
                    rtype = rdef.get('Type')
                    props = rdef.get('Properties') or {}
                    if rtype == 'AWS::Logs::LogGroup':
                        log_name = props.get('LogGroupName')
                        if isinstance(log_name, str) and log_name.strip():
                            props['LogGroupName'] = {'Fn::Sub': '/app/${AWS::StackName}'}
                            yaml_changed = True
                    elif rtype == 'AWS::AutoScaling::ScalingPolicy':
                        for key in list(props):
                            if key.strip().lower().replace('_', '') == 'estimatedwarmupseconds':
                                props['EstimatedInstanceWarmupSeconds'] = props.pop(key)
                                yaml_changed = True
                                break
                    elif rtype == 'AWS::S3::Bucket':
                        bucket_name = props.get('BucketName')
                        if bucket_name is None or not _s3_bucket_name_uses_suffix(bucket_name):
                            safe_id = logical_id.lower().replace('_', '-')[:40]
                            props['BucketName'] = {'Fn::Sub': f'app-${{AWS::AccountId}}-${{BucketNameSuffix}}-{safe_id}'}
                            if 'BucketNameSuffix' not in params:
                                params['BucketNameSuffix'] = {'Type': 'String', 'Default': ''}
                            yaml_changed = True
                    elif rtype == 'AWS::S3::BucketPolicy':
                        policy_text = props.pop('PolicyText', None)
                        if policy_text is not None and 'PolicyDocument' not in props:
                            if isinstance(policy_text, str):
                                try:
                                    props['PolicyDocument'] = json.loads(policy_text)
                                except Exception:
                                    props['PolicyDocument'] = policy_text
                            else:
                                props['PolicyDocument'] = policy_text
                            yaml_changed = True
                    elif rtype == 'AWS::CloudFormation::Stack':
                        tb = props.get('TemplateBody')
                        if isinstance(tb, str) and tb.strip():
                            normalized = _normalize_cfn_template_for_provision(tb)
                            if normalized != tb:
                                props['TemplateBody'] = normalized
                                yaml_changed = True
                if yaml_changed:
                    return yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except Exception:
            pass
        return result
    except Exception:
        return template_body


def _strip_cloudfront_from_template(template_body: str) -> str:
    """Remove all AWS::CloudFront::* resources from template and fix Outputs/DependsOn that reference them. Provision ignores CloudFront even if architecture has it."""
    try:
        is_json = template_body.strip().startswith('{')
        if is_json:
            doc = json.loads(template_body)
        else:
            doc = yaml.safe_load(template_body)
        if not doc or not isinstance(doc, dict):
            return template_body
        resources = doc.get('Resources') or {}
        removed_ids = {
            rid for rid, rdef in resources.items()
            if isinstance(rdef, dict) and (rdef.get('Type') or '').startswith('AWS::CloudFront::')
        }
        if not removed_ids:
            return template_body
        for rid in removed_ids:
            resources.pop(rid, None)
        # Remove outputs that reference removed resources
        outputs = doc.get('Outputs') or {}
        to_remove = []
        for out_name, out_def in outputs.items():
            if not isinstance(out_def, dict):
                continue
            val = out_def.get('Value')
            if isinstance(val, dict):
                if val.get('Ref') in removed_ids:
                    to_remove.append(out_name)
                elif 'Fn::GetAtt' in val:
                    att = val['Fn::GetAtt']
                    if isinstance(att, list) and att and att[0] in removed_ids:
                        to_remove.append(out_name)
                    elif isinstance(att, str) and att.split('.')[0] in removed_ids:
                        to_remove.append(out_name)
            elif isinstance(val, list) and len(val) == 2 and val[0] == 'Ref' and val[1] in removed_ids:
                to_remove.append(out_name)
        for k in to_remove:
            outputs.pop(k, None)
        # Remove DependsOn entries that reference removed resources
        for rdef in resources.values():
            if not isinstance(rdef, dict):
                continue
            dep = rdef.get('DependsOn')
            if dep is None:
                continue
            if isinstance(dep, list):
                new_dep = [d for d in dep if d not in removed_ids]
                if len(new_dep) != len(dep):
                    rdef['DependsOn'] = new_dep if new_dep else None
                    if rdef['DependsOn'] is None:
                        del rdef['DependsOn']
            elif dep in removed_ids:
                del rdef['DependsOn']
        if is_json:
            return json.dumps(doc, indent=2)
        return yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception:
        return template_body


def _strip_s3_bucket_names_for_auto_naming(template_body: str) -> str:
    """Remove BucketName from every AWS::S3::Bucket so CloudFormation auto-generates a unique name (e.g. MyStack-MediaBucket-abc123). Per AWS docs: 'If you don't specify a name, AWS CloudFormation generates a unique ID and uses that ID for the bucket name.' Avoids 'already exists' with zero logic."""
    result = template_body
    try:
        is_json = template_body.strip().startswith('{')
        if is_json:
            doc = json.loads(template_body)
        else:
            doc = yaml.safe_load(template_body)
        if doc and isinstance(doc, dict):
            resources = doc.get('Resources') or {}
            changed = False
            for rdef in resources.values():
                if not isinstance(rdef, dict):
                    continue
                rtype = rdef.get('Type')
                props = rdef.get('Properties') or {}
                if rtype == 'AWS::S3::Bucket' and 'BucketName' in props:
                    del props['BucketName']
                    changed = True
                elif rtype == 'AWS::CloudFormation::Stack':
                    tb = props.get('TemplateBody')
                    if isinstance(tb, str) and tb.strip():
                        child = _strip_s3_bucket_names_for_auto_naming(tb)
                        if child != tb:
                            props['TemplateBody'] = child
                            changed = True
            if changed:
                result = json.dumps(doc, indent=2) if is_json else yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception:
        pass
    # String-level fallback: if BucketName still present (parse failed or edge case), remove the BucketName line(s) so we never send a fixed name to CFN
    if 'S3::Bucket' in result and 'BucketName' in result:
        lines = result.split('\n')
        out = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            # Remove line that is only "BucketName:" and its value on same line (YAML or JSON)
            if re.match(r'^["\']?BucketName["\']?\s*:\s*', stripped) or re.match(r'^BucketName\s*:\s*', stripped):
                i += 1
                continue
            out.append(line)
            i += 1
        result = '\n'.join(out)
    return result


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
def get_mcp_server_info() -> dict:
    """
    Return which MCP server is responding (identity and capabilities). Use this to verify
    the UI or deployment agent is calling the correct server (e.g. cfn_mcp_server with S3 auto-naming).
    """
    return {
        "success": True,
        "server": "cfn_mcp_server",
        "description": "CloudFormation builder and provisioner MCP (AgentCore)",
        "provision_behaviors": {
            "s3_auto_naming": True,
            "strip_bucket_name_before_create": True,
            "normalize_scaling_policy_loggroup": True,
        },
    }


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


def _is_three_tier_request(prompt: str) -> bool:
    """Return True if the prompt indicates a 3-tier application."""
    if not prompt or not isinstance(prompt, str):
        return False
    lower = prompt.strip().lower()
    return any(
        phrase in lower
        for phrase in ("3-tier", "three tier", "three-tier", "3 tier", "three tier app", "3-tier app")
    )


def _load_three_tier_template(format: str) -> str:
    """Load the canned 3-tier template from templates/three_tier.yaml; return as YAML or JSON string."""
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    path = os.path.join(template_dir, "three_tier.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            yaml_str = f.read()
    except Exception as e:
        print(f"[build_cfn_template] Failed to load 3-tier template: {e}")
        return ""
    if (format or "yaml").lower() == "json":
        try:
            data = yaml.safe_load(yaml_str)
            return json.dumps(data, indent=2)
        except Exception as e:
            print(f"[build_cfn_template] Failed to convert 3-tier template to JSON: {e}")
            return yaml_str
    return yaml_str


def _is_microservices_request(prompt: str) -> bool:
    """Return True if the prompt indicates a microservices architecture."""
    if not prompt or not isinstance(prompt, str):
        return False
    lower = prompt.strip().lower()
    return any(
        phrase in lower
        for phrase in (
            "microservices",
            "micro services",
            "micro-service",
            "micro service",
            "microservices architecture",
            "microservices platform",
        )
    )


def _is_serverless_rest_request(prompt: str) -> bool:
    """Return True if the prompt indicates a serverless REST API architecture."""
    if not prompt or not isinstance(prompt, str):
        return False
    lower = prompt.strip().lower()
    return any(
        phrase in lower
        for phrase in (
            "serverless rest api",
            "serverless rest",
            "serverless api",
            "serverless architecture",
            "serverless rest api architecture",
        )
    )


def _is_data_pipeline_request(prompt: str) -> bool:
    """Return True if the prompt indicates a data processing pipeline architecture."""
    if not prompt or not isinstance(prompt, str):
        return False
    lower = prompt.strip().lower()
    return any(
        phrase in lower
        for phrase in (
            "data processing pipeline",
            "data pipeline",
            "data pipeline architecture",
            "etl",
            "kinesis",
            "step functions",
            "glue",
            "athena",
        )
    )


def _load_canned_template(filename: str, format: str) -> str:
    """Load a canned template from templates/<filename>; return as YAML or JSON string."""
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    path = os.path.join(template_dir, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            yaml_str = f.read()
    except Exception as e:
        print(f"[build_cfn_template] Failed to load {filename}: {e}")
        return ""
    if (format or "yaml").lower() == "json":
        try:
            data = yaml.safe_load(yaml_str)
            return json.dumps(data, indent=2)
        except Exception as e:
            print(f"[build_cfn_template] Failed to convert {filename} to JSON: {e}")
            return yaml_str
    return yaml_str


# Template IDs for Quick Example buttons (Quoting Agent -> three_tier, etc.)
TEMPLATE_IDS = ("three_tier", "microservices", "serverless_rest_api", "data_pipeline")


@mcp.tool()
def build_cfn_template(prompt: str, format: str = "yaml", template_id: Optional[str] = None) -> dict:
    """
    Build a CloudFormation template from a natural language prompt using Claude.

    Args:
        prompt: Natural language description of the infrastructure
        format: Output format - 'json' or 'yaml' (default: yaml)
        template_id: Optional. When set (e.g. from a Quick Example button), use this canned template.
            One of: three_tier, microservices, serverless_rest_api, data_pipeline.

    Returns:
        dict with success status and generated CloudFormation template
    """
    t0 = time.time()
    try:
        # Button click: use canned template when template_id is provided
        if template_id and template_id in TEMPLATE_IDS:
            if template_id == "three_tier":
                template_str = _load_three_tier_template(format)
            else:
                template_str = _load_canned_template(
                    {"microservices": "microservices.yaml", "serverless_rest_api": "serverless_rest_api.yaml", "data_pipeline": "data_pipeline.yaml"}[template_id],
                    format,
                )
            if template_str:
                _log_timing("total", "build_cfn_template", t0, extra="source=canned")
                return {
                    "success": True,
                    "template": template_str,
                    "format": format or "yaml",
                    "prompt": prompt,
                }
            # fall through if load failed
        if _is_three_tier_request(prompt):
            template_str = _load_three_tier_template(format)
            if template_str:
                _log_timing("total", "build_cfn_template", t0, extra="source=canned")
                return {
                    "success": True,
                    "template": template_str,
                    "format": format or "yaml",
                    "prompt": prompt,
                }
            # fall through to Bedrock if load failed
        if _is_microservices_request(prompt):
            template_str = _load_canned_template("microservices.yaml", format)
            if template_str:
                _log_timing("total", "build_cfn_template", t0, extra="source=canned")
                return {
                    "success": True,
                    "template": template_str,
                    "format": format or "yaml",
                    "prompt": prompt,
                }
            # fall through to Bedrock if load failed
        if _is_serverless_rest_request(prompt):
            template_str = _load_canned_template("serverless_rest_api.yaml", format)
            if template_str:
                _log_timing("total", "build_cfn_template", t0, extra="source=canned")
                return {
                    "success": True,
                    "template": template_str,
                    "format": format or "yaml",
                    "prompt": prompt,
                }
            # fall through to Bedrock if load failed
        if _is_data_pipeline_request(prompt):
            template_str = _load_canned_template("data_pipeline.yaml", format)
            if template_str:
                _log_timing("total", "build_cfn_template", t0, extra="source=canned")
                return {
                    "success": True,
                    "template": template_str,
                    "format": format or "yaml",
                    "prompt": prompt,
                }
            # fall through to Bedrock if load failed
        bedrock = get_bedrock_client()
        print("[build_cfn_template] enable_thinking=False (speed-optimized)")
        # Bare-minimum CFN builder: provision successfully every time. Default VPC only. No CloudFront, no Cognito.
        system_prompt = """CloudFormation expert. Generate a BARE MINIMUM, DEPLOYABLE template that provisions successfully every time.
Goal: create and provision successfully — avoid bells and whistles. Use the account's default VPC only (parameters; provisioner fills them).

DO NOT INCLUDE (never add these):
- CloudFront (AWS::CloudFront::*) — not deployed by provisioner; causes confusion.
- Cognito (AWS::Cognito::*) — no user pools, no UserPoolClient.
- Auto Scaling Group (AWS::AutoScaling::AutoScalingGroup) — never create ASG. Use a single EC2 instance (or fixed number of instances) behind the ALB instead.
- Any VPC/Subnet/IGW/NAT/Route resources — never create AWS::EC2::VPC, Subnet, InternetGateway, NATGateway, EIP, RouteTable, Route, SubnetRouteTableAssociation. Use ONLY Parameters: VpcId, PublicSubnetIds, PrivateSubnetIds. Provisioner auto-fills from account default VPC.
- LaunchConfiguration — use LaunchTemplate only.
- ASG CreationPolicy that requires SUCCESS signals — omit it so stack completes without cfn-signal.
- Fixed LogGroupName — use !Sub '/app/${AWS::StackName}' only for AWS::Logs::LogGroup.
- EC2 TagSpecifications — use Tags (Key/Value list) only on AWS::EC2::Instance.

REQUIRED PARAMETERS (provisioner fills from default VPC if omitted):
  VpcId: Type: AWS::EC2::VPC::Id, Description: Existing VPC (default VPC)
  PublicSubnetIds: Type: List<AWS::EC2::Subnet::Id>, Description: At least 2 subnets for ALB
  PrivateSubnetIds: Type: List<AWS::EC2::Subnet::Id>, Description: At least 2 subnets for app instance and RDS
Every other parameter MUST have a Default so the stack deploys with zero manual input.

VPC/NETWORKING:
- All SecurityGroups: VpcId: !Ref VpcId. ALB: Subnets: !Ref PublicSubnetIds. App EC2 instance: SubnetId from !Ref PrivateSubnetIds (use one subnet). RDS DBSubnetGroup: SubnetIds: !Ref PrivateSubnetIds.
- Security groups: include ingress and egress; never use empty SecurityGroupIngress/SecurityGroupEgress arrays (omit property if no rules).

RDS (if database needed):
- Engine: postgres, EngineVersion: '16' only (major version; do not pin 16.3).
- DBInstanceIdentifier: !Sub 'appDB-${DBInstanceIdentifierSuffix}' with Parameter DBInstanceIdentifierSuffix (Default: appdb). Provisioner auto-injects unique suffix.
- Use AWS::SecretsManager::Secret with GenerateSecretString for password; reference in MasterUserPassword with {{resolve:secretsmanager:...}}. Or ManageMasterUserPassword: true.
- VPCSecurityGroups (exact name — not VpcSecurityGroupIds): list of !Ref to security group.
- DBSubnetGroup with SubnetIds: !Ref PrivateSubnetIds. AllocatedStorage >= 20. StorageType: gp3. Do NOT set Iops/StorageThroughput when AllocatedStorage < 400.
- MasterUsername: dbadmin (never admin). PubliclyAccessible: false.

ALB / TARGET GROUP / EC2 (no ASG):
- ALB and Target Group: omit Name or use short literal (max 32 chars). Never !Sub with AWS::StackName for these.
- Target Group: VpcId: !Ref VpcId, HealthCheckPath: /, HealthCheckProtocol: HTTP.
- Use a single AWS::EC2::Instance (or fixed count) behind the ALB. Register the instance with the target group using AWS::ElasticLoadBalancingV2::TargetGroupTargetAttachment (TargetGroupArn, TargetId: !Ref AppInstance). Add AWS::ElasticLoadBalancingV2::Listener (DefaultActions: Forward to target group) so ALB forwards to the instance.
- EC2 Instance: Tags (list of Key/Value), not TagSpecifications. Use LaunchTemplate (not LaunchConfiguration) for the instance; LaunchTemplate TagSpecifications at resource level use ResourceType: "launch-template" only.

LAMBDA (if needed):
- Inline ZipFile only; no S3 code. Runtime: python3.12 or nodejs20.x. Include execution role with logs permissions. Omit FunctionName or use short literal (max 64 chars).

S3 (if needed):
- BucketName: !Sub 'app-${AWS::AccountId}-${BucketNameSuffix}' with Parameter BucketNameSuffix (Default: files or any). Provisioner always injects a unique suffix on create so the bucket name never collides (e.g. app-471112858498-12345678).

API GATEWAY (if needed):
- REST: AWS::ApiGateway::Deployment must have DependsOn on ALL Method resources. Stage: do NOT put LoggingLevel/DataTraceEnabled at Stage root; use MethodSettings if needed. PathPart: only a-zA-Z0-9._-: or {name} (e.g. {itemId} not {item-id}). Lambda permission required.

LOGS:
- AWS::Logs::LogGroup: LogGroupName must be !Sub '/app/${AWS::StackName}' (unique per stack).

OUTPUT: Return ONLY valid YAML. No markdown fences. Every Ref/GetAtt must reference a resource in the template. All parameters must have Default except VpcId/PublicSubnetIds/PrivateSubnetIds (provisioner fills those from default VPC). Keep the generated template as small as possible while still correct (reduces latency).

MINIMAL EXAMPLE (stay close to this pattern — default VPC params, Secrets Manager for RDS, no VPC resources in Resources):
---
AWSTemplateFormatVersion: '2010-09-09'
Description: Three-tier app with ALB, single EC2 instance, RDS — uses existing VPC (no ASG)
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
        # Inject official schema hints for key resource types (reduces deploy failures). Skip if BUILD_CFN_FAST=true to save ~2-4s and stay under AgentCore 60s tool timeout.
        if os.environ.get("BUILD_CFN_FAST", "").lower() not in ("true", "1", "yes"):
            try:
                schema_parts = [_schema_summary_for_builder(rt) for rt in _KEY_SCHEMA_TYPES_FOR_BUILDER]
                if schema_parts:
                    system_prompt += "\n\nOFFICIAL SCHEMA HINTS (use exact property names and required fields where applicable):\n" + "\n".join(schema_parts)
            except Exception:
                pass
        user_message = f"""Generate a CloudFormation template for: {prompt}

Format: {format.upper()}. Verify every Ref and GetAtt points to a defined resource. Return ONLY the template. Keep it minimal."""
        t_bedrock = time.time()
        # CRITICAL: enable_thinking=False for speed. AgentCore enforces ~60s MCP tool timeout; keep under by using
        # BEDROCK_MODEL_ID_CFN_BUILDER (default Haiku), max_tokens 16384, and minimal output.
        response = converse_with_retry(
            bedrock, BEDROCK_MODEL_ID_CFN_BUILDER, system_prompt, user_message, max_tokens=16384, enable_thinking=False,
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


def _normalize_template_for_validation(template_body) -> str:
    """Ensure template is a string, strip, and replace tabs (CloudFormation rejects tabs in YAML)."""
    if template_body is None:
        return ""
    if isinstance(template_body, dict):
        return json.dumps(template_body, indent=2)
    s = str(template_body).strip()
    if "\t" in s:
        s = s.replace("\t", "  ")
    return s


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
    template_body = _normalize_template_for_validation(template_body)
    if not template_body:
        return {
            "success": False,
            "valid": False,
            "error": "Template body is empty. Generate a template in Onboarding Agent first.",
            "violations": [{
                "rule_id": "TemplateValidation",
                "severity": "ERROR",
                "resource": "",
                "resource_type": "",
                "message": "Template body is empty.",
                "remediation": "Generate infrastructure in Onboarding Agent, then validate the template.",
            }],
        }
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
    # Ignore CloudFront: remove all AWS::CloudFront::* resources so we never provision them (cache policy / OAC quirks)
    template_body = _strip_cloudfront_from_template(template_body)
    # Let CloudFormation auto-name S3 buckets (remove BucketName so CFN generates unique ID — avoids "already exists")
    template_body = _strip_s3_bucket_names_for_auto_naming(template_body)
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
                {'Key': 'resourcename', 'Value': 'sfmwcdemo'},
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
        # When parse failed, detect VPC param names from template body so default VPC fill still works
        if not template_param_keys and ('Parameters' in template_body or '"Parameters"' in template_body):
            for name in ('VpcId', 'PublicSubnetIds', 'PrivateSubnetIds', 'SubnetId'):
                if re.search(r'["\']?' + re.escape(name) + r'["\']?\s*[:{]', template_body):
                    template_param_keys.add(name)
        # Keys that must never be sent as literal "default" (match case-insensitively)
        VPC_PARAM_KEYS = ('VpcId', 'PublicSubnetIds', 'PrivateSubnetIds', 'SubnetId')
        def _is_vpc_param_key(key):
            return (key or '').strip().lower() in ('vpcid', 'publicsubnetids', 'privatesubnetids', 'subnetid')
        def _use_default_vpc_value(key):
            val = (user_params.get(key) or '').strip().lower()
            return not val or val == 'default'
        # Check if we need to resolve VPC: template has these params (parsed or detected in body) or client sent them
        template_has_vpc_params = any(k for k in template_param_keys if _is_vpc_param_key(k))
        if not template_has_vpc_params and ('Parameters' in template_body or '"Parameters"' in template_body):
            for name in ('VpcId', 'PublicSubnetIds', 'PrivateSubnetIds', 'SubnetId'):
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
            # ALB cannot have two subnets in the same AZ; use at most one subnet per AZ
            if default_subnet_ids:
                default_subnet_ids = _one_subnet_per_az(default_subnet_ids)
            if default_vpc_id and default_subnet_ids:
                subnet_val = ','.join(default_subnet_ids)
                for key in list(user_params.keys()):
                    if not _is_vpc_param_key(key):
                        continue
                    if not _use_default_vpc_value(key):
                        continue
                    if key.strip().lower() == 'vpcid':
                        user_params[key] = default_vpc_id
                    elif key.strip().lower() == 'subnetid':
                        user_params[key] = default_subnet_ids[0] if default_subnet_ids else ''
                    else:
                        user_params[key] = subnet_val
                # Only set VPC params that actually exist in the template (avoid ValidationError "do not exist in the template")
                for ckey in VPC_PARAM_KEYS:
                    if ckey in template_param_keys and _use_default_vpc_value(ckey):
                        if ckey == 'VpcId':
                            user_params[ckey] = default_vpc_id
                        elif ckey == 'SubnetId':
                            user_params[ckey] = default_subnet_ids[0] if default_subnet_ids else ''
                        else:
                            user_params[ckey] = subnet_val
            for key in list(user_params.keys()):
                if _is_vpc_param_key(key) and _use_default_vpc_value(key):
                    hint = 'Pass explicit VpcId/PublicSubnetIds/PrivateSubnetIds, or ensure the target account has a default VPC.'
                    if _get_cross_account_role_arn():
                        hint += ' For cross-account, you can set CFN_TARGET_DEFAULT_VPC_ID to a VPC ID in the target account.'
                    else:
                        hint += ' Or ensure vpc-0ca2fc76 exists in this region and has subnets.'
                    return {
                        'success': False,
                        'error': f'Could not resolve default VPC/subnets for {key}. {hint}',
                    }
        # Auto-inject short unique suffixes on create (timestamp last 8 digits) to avoid "already exists"
        unique_suffix = str(int(time.time()))[-8:]
        if not stack_exists:
            def _is_db_suffix_key(k):
                return (k or '').strip().lower() == 'dbinstanceidentifiersuffix'
            _db_suffix_key = next((k for k in template_param_keys if _is_db_suffix_key(k)), None)
            template_has_db_suffix = _db_suffix_key is not None or 'DBInstanceIdentifierSuffix' in template_body or 'dbinstanceidentifiersuffix' in template_body.lower()
            if template_has_db_suffix:
                key_to_set = _db_suffix_key or 'DBInstanceIdentifierSuffix'
                user_params[key_to_set] = unique_suffix
                template_param_keys.add(key_to_set)  # ensure we send it even if parse had failed earlier
            # S3: always inject unique BucketNameSuffix on create (we strip BucketName so this is rarely needed; keep for templates that reference it)
            def _is_bucket_suffix_key(k):
                return (k or '').strip().lower() == 'bucketnamesuffix'
            _bucket_suffix_key = next((k for k in template_param_keys if _is_bucket_suffix_key(k)), None)
            template_has_bucket_suffix = _bucket_suffix_key is not None or 'BucketNameSuffix' in template_body or 'bucketnamesuffix' in template_body.lower()
            if template_has_bucket_suffix:
                key_to_set = _bucket_suffix_key or 'BucketNameSuffix'
                user_params[key_to_set] = unique_suffix
                template_param_keys.add(key_to_set)
        # Final safeguard: never send literal "default" for VPC params to CloudFormation.
        # Only send parameters that exist in the template to avoid "Parameters [...] do not exist in the template".
        if user_params:
            params['Parameters'] = []
            for k, v in user_params.items():
                if _is_vpc_param_key(k) and (v or '').strip().lower() == 'default':
                    continue
                if template_param_keys and k not in template_param_keys:
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
