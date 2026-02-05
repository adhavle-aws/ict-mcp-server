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


@mcp.tool()
def generate_architecture_overview(prompt: str) -> dict:
    """
    Generate a comprehensive architecture overview from requirements.
    Returns markdown with reasoning, component details, and ASCII diagram with AWS icons.
    """
    try:
        bedrock = get_bedrock_client()
        
        system_prompt = """Senior AWS Solutions Architect. Create concise architecture overviews.

Include:
1. Executive Summary (2 sentences)
2. Architecture Diagram (ASCII with AWS emojis: 🌐 ALB, 🖥️ EC2, 📦 S3, 🗄️ RDS, λ Lambda, 🔐 IAM)
3. Component List (service + purpose only)
4. Security (key points only)"""

        user_message = f"""Create concise architecture overview for: {prompt}"""

        response = call_bedrock_with_retry(
            bedrock,
            'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 1024,  # Reduced from 2048 for faster response
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            }
        )
        
        response_body = json.loads(response['body'].read())
        overview = response_body['content'][0]['text']
        
        return {
            'success': True,
            'overview': overview
        }
    except Exception as e:
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
    try:
        bedrock = get_bedrock_client()
        
        # Create prompt for Claude
        system_prompt = """CloudFormation expert. Generate VALID, correct templates.

CRITICAL Rules:
1. ALL resource references (Ref, GetAtt, DependsOn) MUST point to resources defined in the template
2. Check every Ref and GetAtt - ensure the resource exists
3. Use correct resource names (case-sensitive)
4. Include AWSTemplateFormatVersion: '2010-09-09'
5. Return ONLY valid YAML/JSON, no explanations"""

        user_message = f"""Generate valid CloudFormation template for: {prompt}

Format: {format.upper()}

CRITICAL: Verify all Ref and GetAtt references point to defined resources.

Return ONLY the template."""

        # Call Claude via Bedrock with retry
        response = call_bedrock_with_retry(
            bedrock,
            'global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 16384,  # Maximum for complex enterprise templates
                'system': system_prompt,
                'messages': [
                    {
                        'role': 'user',
                        'content': user_message
                    }
                ]
            }
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        template_str = response_body['content'][0]['text'].strip()
        
        # Clean up markdown code blocks if present
        if template_str.startswith('```'):
            lines = template_str.split('\n')
            template_str = '\n'.join(lines[1:-1])
        
        return {
            'success': True,
            'template': template_str,
            'format': format,
            'prompt': prompt
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


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
        return {
            'success': True,
            'valid': True,
            'capabilities': response.get('Capabilities', []),
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
4. Return ONLY the fixed template
5. No explanations"""

            user_message = f"""Fix this CloudFormation validation error:

ERROR: {error_message}

TEMPLATE:
{template_body}

Common fixes:
- If resource not found: Check spelling, add missing resource, or remove reference
- If GetAtt fails: Verify resource exists and attribute is valid
- If DependsOn fails: Ensure dependency resource exists

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
def provision_cfn_stack(stack_name: str, template_body: str, capabilities: list = None) -> dict:
    """Create or update a CloudFormation stack"""
    cfn = get_cfn_client()
    try:
        # Check if stack exists
        try:
            cfn.describe_stacks(StackName=stack_name)
            stack_exists = True
        except:
            stack_exists = False
        
        params = {
            'StackName': stack_name,
            'TemplateBody': template_body
        }
        
        if capabilities:
            params['Capabilities'] = capabilities
        
        if stack_exists:
            response = cfn.update_stack(**params)
            action = 'updated'
        else:
            response = cfn.create_stack(**params)
            action = 'created'
        
        return {
            'success': True,
            'action': action,
            'stack_id': response['StackId']
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }



@mcp.tool()
def analyze_cost_optimization(prompt: str = None, template_body: str = None) -> dict:
    """
    Analyze cost optimization opportunities from requirements or CloudFormation template.
    """
    try:
        if not prompt and not template_body:
            return {'success': False, 'error': 'Either prompt or template_body must be provided'}
        
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS cost optimization expert. Analyze architectures and provide specific, actionable cost-saving recommendations that directly reference the components and findings from the Well-Architected Review.

CRITICAL: Build upon the Well-Architected Review findings. Reference specific recommendations and risks identified. Provide concrete cost estimates and savings calculations."""

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
            user_message = f"""Analyze cost optimization based on this Well-Architected Review:

WELL-ARCHITECTED REVIEW FINDINGS:
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
   - Reference the specific Well-Architected findings above
   - Provide alternatives for expensive components
   - Consider the trade-offs mentioned in the review (reliability vs cost)

4. Estimated Savings:
   - Provide specific dollar amounts or percentages
   - Show before/after cost comparison

5. Implementation Roadmap:
   - Quick wins (< 1 week)
   - Medium-term optimizations (1-4 weeks)
   - Long-term strategies (1-3 months)

IMPORTANT: Reference the specific architecture components and Well-Architected findings. Don't provide generic cost advice."""

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
    Perform AWS Well-Architected Framework review on requirements or CloudFormation template.
    """
    try:
        if not prompt and not template_body:
            return {'success': False, 'error': 'Either prompt or template_body must be provided'}
        
        bedrock = get_bedrock_client()
        
        system_prompt = """AWS Well-Architected expert. Review against 6 pillars with specific recommendations."""

        if template_body:
            user_message = f"""Review CloudFormation template (6 pillars):

{template_body}

For each pillar: Assessment, Risks, Recommendations (High/Medium/Low priority)"""
        elif prompt:
            user_message = f"""Review architecture (6 pillars):

{prompt}

For each pillar: Assessment, Strengths, Risks, Recommendations (priority)"""

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
