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
def generate_architecture_overview(prompt: str) -> dict:
    """
    Generate a comprehensive architecture overview from requirements.
    Returns markdown with reasoning, component details, and ASCII diagram with AWS icons.
    """
    try:
        bedrock = get_bedrock_client()
        
        system_prompt = """You are a Senior AWS Solutions Architect. Analyze requirements and create comprehensive architecture overviews with clear reasoning for every decision.

Your response must include:
1. Executive Summary (2-3 sentences)
2. Architecture Diagram (ASCII art with AWS service icons/emojis)
3. Component Breakdown (each service with purpose and rationale)
4. Design Decisions (why you chose each service/pattern)
5. Data Flow (how requests move through the system)
6. Security Considerations (specific to this architecture)

Use emojis/icons for AWS services:
- 🌐 ALB/CloudFront
- 🖥️ EC2
- 📦 S3
- 🗄️ RDS/DynamoDB
- λ Lambda
- 🔐 IAM/Security Groups
- 🌍 VPC
- 🔄 Auto Scaling

Be specific and provide reasoning for every architectural choice."""

        user_message = f"""Analyze these requirements and create a comprehensive architecture overview:

REQUIREMENTS:
{prompt}

Provide:

## Executive Summary
Brief overview of what we're building and why

## Architecture Diagram
Create an ASCII diagram using AWS service icons/emojis showing:
- All tiers/layers
- AWS services
- Data flow with arrows
- Network boundaries

Example format:
```
Internet
   ↓
🌐 Application Load Balancer
   ↓
🖥️ Web Tier (EC2 Auto Scaling)
   ↓
🖥️ App Tier (EC2 Auto Scaling)
   ↓
🗄️ Database Tier (RDS Multi-AZ)
```

## Component Breakdown
For each AWS service:
- **Service Name** (icon)
- Purpose: What it does
- Configuration: Key settings
- Rationale: WHY we chose this service/configuration

## Design Decisions
Explain the reasoning behind:
- Architecture pattern chosen (3-tier, serverless, etc.)
- Service selections (why EC2 vs Lambda, why RDS vs DynamoDB)
- Network design (public/private subnets, Multi-AZ)
- Scaling strategy
- Security approach

## Data Flow
Step-by-step request flow:
1. User request arrives at...
2. ALB routes to...
3. Web tier processes...
etc.

## Security Architecture
- Network isolation strategy
- Access control approach
- Encryption decisions
- Compliance considerations

Be specific and provide concrete reasoning for every choice."""

        response = call_bedrock_with_retry(
            bedrock,
            'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 3072,
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

        # Call Claude via Bedrock with retry
        response = call_bedrock_with_retry(
            bedrock,
            'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
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
            'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
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
        
        system_prompt = """You are an AWS Well-Architected Framework expert. Review architectures against the 6 pillars and provide specific, actionable recommendations that directly reference the architecture being reviewed.

CRITICAL: Your review must be specific to the architecture provided, not generic best practices. Reference specific components, services, and design decisions mentioned in the architecture."""

        if template_body:
            user_message = f"""Review this CloudFormation template against AWS Well-Architected Framework:

{template_body}

For each pillar, provide:
1. Assessment of the SPECIFIC resources and configurations in this template
2. Risks identified in THIS architecture
3. Recommendations that reference SPECIFIC resources by name
4. Priority level (High/Medium/Low)

Be specific - reference actual resource names and configurations from the template."""
        elif prompt:
            user_message = f"""Review this architecture against AWS Well-Architected Framework:

ARCHITECTURE TO REVIEW:
{prompt}

For each of the 6 pillars (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, Sustainability), provide:

1. Assessment: Analyze the SPECIFIC components mentioned (ALB, EC2, RDS, etc.) - not generic advice
2. Strengths: What this architecture does well
3. Risks: Specific risks based on the components and design described
4. Recommendations: Actionable improvements that reference the actual services mentioned
5. Priority: High/Medium/Low

IMPORTANT: Reference the specific services, tiers, and components mentioned in the architecture. Don't provide generic AWS advice - make it specific to THIS 3-tier application design."""

        response = call_bedrock_with_retry(
            bedrock,
            'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
            {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
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
