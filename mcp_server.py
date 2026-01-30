# mcp_server.py
from mcp.server.fastmcp import FastMCP
import boto3
import yaml
import json
import os

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


@mcp.tool()
def build_cfn_template(prompt: str, format: str = "yaml") -> dict:
    """
    Build a CloudFormation template from a natural language prompt using Claude.
    
    Args:
        prompt: Natural language description of the infrastructure
        format: Output format - 'json' or 'yaml' (default: yaml)
    
    Returns:
        dict with success status, generated CloudFormation template, and thinking process
    """
    try:
        bedrock = get_bedrock_client()
        
        # Create prompt for Claude with extended thinking
        system_prompt = """You are a CloudFormation expert. Generate valid CloudFormation templates based on user requirements.

Rules:
1. Return ONLY valid CloudFormation YAML/JSON
2. Include AWSTemplateFormatVersion: '2010-09-09'
3. Use proper resource types and properties
4. Follow AWS best practices
5. Add appropriate resource names
6. Return ONLY the template, no explanations"""

        user_message = f"""Generate a CloudFormation template for: {prompt}

Output format: {format.upper()}

Return ONLY the CloudFormation template, nothing else."""

        # Call Claude via Bedrock with extended thinking
        response = bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'thinking': {
                    'type': 'enabled',
                    'budget_tokens': 2000
                },
                'system': system_prompt,
                'messages': [
                    {
                        'role': 'user',
                        'content': user_message
                    }
                ]
            })
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        
        # Extract thinking and template
        thinking = ''
        template_str = ''
        
        for content in response_body['content']:
            if content['type'] == 'thinking':
                thinking = content['thinking']
            elif content['type'] == 'text':
                template_str = content['text'].strip()
        
        # Clean up markdown code blocks if present
        if template_str.startswith('```'):
            lines = template_str.split('\n')
            template_str = '\n'.join(lines[1:-1])
        
        return {
            'success': True,
            'template': template_str,
            'format': format,
            'prompt': prompt,
            'thinking': thinking
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@mcp.tool()
def validate_cfn_template(template_body: str) -> dict:
    """Validate a CloudFormation template using AWS API"""
    cfn = get_cfn_client()
    try:
        response = cfn.validate_template(TemplateBody=template_body)
        return {
            'success': True,
            'valid': True,
            'capabilities': response.get('Capabilities', [])
        }
    except Exception as e:
        return {
            'success': False,
            'valid': False,
            'error': str(e)
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
def generate_architecture_diagram(template_body: str) -> dict:
    """
    Generate a visual architecture diagram from CloudFormation template using Claude.
    Returns a text-based architecture overview.
    """
    try:
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS architecture expert. Analyze CloudFormation templates and create visual architecture diagrams.

Create a clear, text-based architecture diagram showing:
1. All AWS resources and their relationships
2. Network flow and connectivity
3. Security boundaries
4. Data flow

Use ASCII art or structured text format."""

        user_message = f"""Analyze this CloudFormation template and create a visual architecture diagram:

{template_body}

Provide:
1. ASCII architecture diagram
2. Resource list with descriptions
3. Network topology
4. Security groups and access patterns"""

        response = bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            })
        )
        
        response_body = json.loads(response['body'].read())
        diagram = response_body['content'][0]['text']
        
        return {
            'success': True,
            'diagram': diagram
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@mcp.tool()
def analyze_cost_optimization(template_body: str) -> dict:
    """
    Analyze CloudFormation template for cost optimization opportunities using Claude.
    """
    try:
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS cost optimization expert. Analyze CloudFormation templates and provide cost-saving recommendations.

Focus on:
1. Right-sizing resources
2. Reserved instances vs on-demand
3. Storage optimization
4. Network cost reduction
5. Serverless alternatives"""

        user_message = f"""Analyze this CloudFormation template for cost optimization:

{template_body}

Provide:
1. Current cost drivers
2. Optimization recommendations
3. Estimated savings
4. Implementation priority"""

        response = bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            })
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
def well_architected_review(template_body: str) -> dict:
    """
    Perform AWS Well-Architected Framework review on CloudFormation template using Claude.
    """
    try:
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS Well-Architected Framework expert. Review CloudFormation templates against the 6 pillars:

1. Operational Excellence
2. Security
3. Reliability
4. Performance Efficiency
5. Cost Optimization
6. Sustainability

Provide specific, actionable recommendations."""

        user_message = f"""Review this CloudFormation template against AWS Well-Architected Framework:

{template_body}

For each pillar, provide:
1. Current state assessment
2. Risks identified
3. Recommendations
4. Priority level (High/Medium/Low)"""

        response = bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            })
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
