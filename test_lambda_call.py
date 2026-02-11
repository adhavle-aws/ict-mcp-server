#!/usr/bin/env python3
"""Test calling AgentCore the same way Lambda does"""
import json
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib.request

# Deployed via deploy-agentcore.sh (cfn_mcp_server)
AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:611291728384:runtime/cfn_mcp_server-4KOBaDFd4a"
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

# Test build_cfn_template with short prompt
prompt_short = "3-tier web app with ALB, EC2, and RDS in us-east-1"

print("Testing build_cfn_template with SHORT prompt...")
result = call_mcp_tool('build_cfn_template', {'prompt': prompt_short, 'format': 'yaml'})
print(f"\nResult keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
if isinstance(result, dict) and result.get('success') and result.get('template'):
    print(f"Template length: {len(result['template'])} chars")
else:
    print(f"Result: {json.dumps(result, indent=2)[:500]}")
