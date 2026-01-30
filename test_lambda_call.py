#!/usr/bin/env python3
"""Test calling AgentCore the same way Lambda does"""
import json
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib.request

AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-VpWbdyCLTH"
REGION = "us-east-1"

def call_mcp_tool(tool_name, arguments):
    """Call MCP server via AgentCore (same as Lambda)"""
    session = boto3.Session()
    credentials = session.get_credentials()
    
    encoded_arn = AGENT_ARN.replace(':', '%3A').replace('/', '%2F')
    mcp_url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    
    request_body = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {
            'name': tool_name,
            'arguments': arguments
        }
    })
    
    aws_request = AWSRequest(
        method='POST',
        url=mcp_url,
        data=request_body,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        }
    )
    
    SigV4Auth(credentials, 'bedrock-agentcore', REGION).add_auth(aws_request)
    
    req = urllib.request.Request(
        mcp_url,
        data=request_body.encode('utf-8'),
        headers=dict(aws_request.headers)
    )
    
    with urllib.request.urlopen(req, timeout=120) as response:
        response_data = response.read().decode('utf-8')
        print(f"Response data length: {len(response_data)}")
        print(f"Response starts with: {response_data[:100]}")
        
        if not response_data.strip():
            return {'error': 'Empty response from AgentCore'}
        
        # Parse SSE format (may start with ping or event)
        if 'event:' in response_data:
            print("Parsing as SSE format")
            lines = response_data.split('\n')
            for line in lines:
                if line.startswith('data: '):
                    json_data = line[6:]
                    result = json.loads(json_data)
                    return result
            return {'error': 'No data line in SSE response'}
        else:
            print("Parsing as JSON")
            return json.loads(response_data)

# Test with short prompt
arch_overview_short = "3-tier web app with ALB, EC2, and RDS in us-east-1"

print("Testing well_architected_review with SHORT prompt...")
result = call_mcp_tool('well_architected_review', {'prompt': arch_overview_short})
print(f"\nResult: {json.dumps(result, indent=2)[:500]}")

# Test with long prompt
arch_overview_long = """Here's the architecture overview: A highly available 3-tier web application architecture in AWS US-East-1 region consisting of: Web tier (presentation layer), Application tier (business logic), Database tier (data storage). Key Components: Web Tier with ALB and Auto Scaling, Application Tier with EC2 in private subnets, Database Tier with RDS Multi-AZ."""

print("\n\nTesting well_architected_review with LONG prompt...")
result2 = call_mcp_tool('well_architected_review', {'prompt': arch_overview_long})
print(f"\nResult: {json.dumps(result2, indent=2)[:500]}")
