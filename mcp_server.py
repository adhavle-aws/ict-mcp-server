# mcp_server.py
from mcp.server.fastmcp import FastMCP
import boto3
import yaml
import json
import os
import subprocess
import tempfile
import base64
from pathlib import Path

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
def generate_architecture_overview(prompt: str) -> dict:
    """
    Generate a text-based architecture overview from requirements.
    Returns markdown summary of what will be built and how.
    """
    try:
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS Solutions Architect. Analyze requirements and create clear architecture overviews.

Provide:
1. What we're building (high-level summary)
2. Key components and their purpose
3. How components interact
4. Architecture patterns used
5. AWS services selected and why

Use clear, concise markdown format."""

        user_message = f"""Analyze these requirements and create an architecture overview:

{prompt}

Provide a clear summary of:
- What we're building
- Key AWS services and components
- How they work together
- Architecture patterns and best practices"""

        response = bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 2048,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': user_message}]
            })
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

        # Call Claude via Bedrock
        response = bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
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
    Generate a professional visual architecture diagram from CloudFormation template 
    using AWS Diagram MCP Server (Python diagrams package with official AWS icons).
    
    Returns base64-encoded PNG image that can be displayed in the UI.
    """
    try:
        print(f"Diagram generation - template length: {len(template_body)}")
        print(f"Template starts with: {template_body[:100]}")
        
        # Parse CloudFormation template to extract resources
        resources = parse_cfn_resources(template_body)
        
        print(f"Found {len(resources)} resources")
        
        if not resources:
            return {
                'success': False,
                'error': f'No resources found in template. Template length: {len(template_body)}, starts with: {template_body[:50]}'
            }
        
        # Generate Python code for diagrams package
        diagram_code = generate_diagram_code(resources, template_body)
        
        # Execute diagram generation
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write Python code to temp file
            code_file = Path(tmpdir) / "diagram.py"
            code_file.write_text(diagram_code)
            
            # Execute the diagram code
            result = subprocess.run(
                ['python3', str(code_file)],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': f'Diagram generation failed: {result.stderr}'
                }
            
            # Find generated PNG file
            png_files = list(Path(tmpdir).glob('*.png'))
            if not png_files:
                return {
                    'success': False,
                    'error': 'No diagram image generated'
                }
            
            # Read and encode image as base64
            with open(png_files[0], 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            return {
                'success': True,
                'image': image_data,
                'format': 'png',
                'encoding': 'base64',
                'resources_count': len(resources)
            }
            
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Diagram generation timed out'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def parse_cfn_resources(template_body: str) -> list:
    """Parse CloudFormation template to extract resources"""
    resources = []
    
    try:
        print(f"Template type: {type(template_body)}")
        print(f"Template first 200 chars: {repr(template_body[:200])}")
        
        # Try parsing as YAML first
        try:
            template = yaml.safe_load(template_body)
            print(f"Parsed as YAML. Keys: {list(template.keys())}")
        except Exception as yaml_error:
            print(f"YAML parsing failed: {yaml_error}")
            # Try JSON
            template = json.loads(template_body)
            print(f"Parsed as JSON. Keys: {list(template.keys())}")
        
        if 'Resources' in template:
            print(f"Found Resources section with {len(template['Resources'])} resources")
            for name, resource in template['Resources'].items():
                resources.append({
                    'name': name,
                    'type': resource.get('Type', 'Unknown'),
                    'properties': resource.get('Properties', {})
                })
        else:
            print(f"No Resources section found. Template keys: {list(template.keys())}")
    except Exception as e:
        print(f"Error parsing template: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"Returning {len(resources)} resources")
    return resources


def generate_diagram_code(resources: list, template_body: str) -> str:
    """Generate Python code using diagrams package for AWS architecture"""
    
    # Map CFN resource types to diagrams package classes
    resource_map = {
        'AWS::Lambda::Function': ('compute', 'Lambda'),
        'AWS::ApiGatewayV2::Api': ('network', 'APIGateway'),
        'AWS::ApiGateway::RestApi': ('network', 'APIGateway'),
        'AWS::DynamoDB::Table': ('database', 'Dynamodb'),
        'AWS::S3::Bucket': ('storage', 'S3'),
        'AWS::RDS::DBInstance': ('database', 'RDS'),
        'AWS::EC2::Instance': ('compute', 'EC2'),
        'AWS::ECS::Service': ('compute', 'ECS'),
        'AWS::ECS::TaskDefinition': ('compute', 'ECS'),
        'AWS::ElasticLoadBalancingV2::LoadBalancer': ('network', 'ELB'),
        'AWS::Cognito::UserPool': ('security', 'Cognito'),
        'AWS::SNS::Topic': ('integration', 'SNS'),
        'AWS::SQS::Queue': ('integration', 'SQS'),
        'AWS::IAM::Role': ('security', 'IAM'),
        'AWS::CloudFront::Distribution': ('network', 'CloudFront'),
        'AWS::Route53::RecordSet': ('network', 'Route53'),
        'AWS::ElastiCache::CacheCluster': ('database', 'ElastiCache'),
        'AWS::StepFunctions::StateMachine': ('integration', 'StepFunctions'),
        'AWS::EventBridge::Rule': ('integration', 'Eventbridge'),
        'AWS::Kinesis::Stream': ('analytics', 'KinesisDataStreams'),
    }
    
    # Generate imports
    imports = set()
    for resource in resources:
        res_type = resource['type']
        if res_type in resource_map:
            category, class_name = resource_map[res_type]
            imports.add(f"from diagrams.aws.{category} import {class_name}")
    
    # Build diagram code
    code = """from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda, EC2, ECS
from diagrams.aws.network import APIGateway, ELB, CloudFront, Route53
from diagrams.aws.database import Dynamodb, RDS, ElastiCache
from diagrams.aws.storage import S3
from diagrams.aws.security import Cognito, IAM
from diagrams.aws.integration import SNS, SQS, StepFunctions, Eventbridge
from diagrams.aws.analytics import KinesisDataStreams

with Diagram("AWS Architecture", show=False, direction="LR"):
"""
    
    # Add resources
    for i, resource in enumerate(resources):
        res_type = resource['type']
        res_name = resource['name']
        
        if res_type in resource_map:
            category, class_name = resource_map[res_type]
            # Truncate long names
            display_name = res_name[:20] + '...' if len(res_name) > 20 else res_name
            code += f'    {res_name.lower().replace("-", "_")} = {class_name}("{display_name}")\n'
        else:
            # Use generic compute for unknown types
            display_name = res_name[:20] + '...' if len(res_name) > 20 else res_name
            code += f'    {res_name.lower().replace("-", "_")} = EC2("{display_name}")\n'
    
    # Add simple connections (chain resources)
    if len(resources) > 1:
        code += "\n    # Connections\n"
        for i in range(len(resources) - 1):
            curr = resources[i]['name'].lower().replace("-", "_")
            next_res = resources[i + 1]['name'].lower().replace("-", "_")
            code += f"    {curr} >> {next_res}\n"
    
    return code


@mcp.tool()
def analyze_cost_optimization(prompt: str = None, template_body: str = None) -> dict:
    """
    Analyze cost optimization opportunities from requirements or CloudFormation template.
    """
    try:
        if not prompt and not template_body:
            return {'success': False, 'error': 'Either prompt or template_body must be provided'}
        
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS cost optimization expert. Analyze requirements or templates and provide cost-saving recommendations.

Focus on:
1. Right-sizing resources
2. Reserved instances vs on-demand
3. Storage optimization
4. Network cost reduction
5. Serverless alternatives"""

        if template_body:
            user_message = f"""Analyze this CloudFormation template for cost optimization:

{template_body}

Provide:
1. Current cost drivers
2. Optimization recommendations
3. Estimated savings
4. Implementation priority"""
        elif prompt:
            user_message = f"""Analyze these requirements for cost optimization:

{prompt}

Provide:
1. Potential cost drivers
2. Cost-effective architecture recommendations
3. Estimated costs
4. Cost optimization strategies"""

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
def well_architected_review(prompt: str = None, template_body: str = None) -> dict:
    """
    Perform AWS Well-Architected Framework review on requirements or CloudFormation template.
    """
    try:
        if not prompt and not template_body:
            return {'success': False, 'error': 'Either prompt or template_body must be provided'}
        
        bedrock = get_bedrock_client()
        
        system_prompt = """You are an AWS Well-Architected Framework expert. Review requirements or templates against the 6 pillars:

1. Operational Excellence
2. Security
3. Reliability
4. Performance Efficiency
5. Cost Optimization
6. Sustainability

Provide specific, actionable recommendations."""

        if template_body:
            user_message = f"""Review this CloudFormation template against AWS Well-Architected Framework:

{template_body}

For each pillar, provide:
1. Current state assessment
2. Risks identified
3. Recommendations
4. Priority level (High/Medium/Low)"""
        elif prompt:
            user_message = f"""Review these requirements against AWS Well-Architected Framework:

{prompt}

For each pillar, provide:
1. Architecture recommendations
2. Potential risks
3. Best practices to follow
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
