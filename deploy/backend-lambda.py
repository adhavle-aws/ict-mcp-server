"""
Lambda function for backend proxy
Handles AWS SigV4 signing for AgentCore Runtime
"""
import json
import boto3
import os
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib.request
import urllib.parse

AGENT_ARN = os.environ['AGENT_ARN']
REGION = os.environ.get('AWS_REGION', 'us-east-1')

def lambda_handler(event, context):
    """Lambda handler for API Gateway"""
    
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        
        # Get AWS credentials
        session = boto3.Session()
        credentials = session.get_credentials()
        
        # Encode ARN
        encoded_arn = AGENT_ARN.replace(':', '%3A').replace('/', '%2F')
        mcp_url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        
        # Prepare request
        request_body = json.dumps(body)
        
        # Create AWS request for signing
        aws_request = AWSRequest(
            method='POST',
            url=mcp_url,
            data=request_body,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
            }
        )
        
        # Sign with SigV4
        SigV4Auth(credentials, 'bedrock-agentcore', REGION).add_auth(aws_request)
        
        # Make request
        req = urllib.request.Request(
            mcp_url,
            data=request_body.encode('utf-8'),
            headers=dict(aws_request.headers)
        )
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps(result)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }
