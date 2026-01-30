"""
Lambda handler for CloudFormation Builder Backend
Direct HTTP approach with SigV4 signing (no persistent MCP session)
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum
import boto3
import os
import json
import urllib.request
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

app = FastAPI(title="CloudFormation MCP Backend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from environment
AGENT_ARN = os.environ.get('AGENT_ARN')
REGION = os.environ.get('REGION', 'us-east-1')

def get_mcp_url():
    """Get MCP endpoint URL"""
    encoded_arn = AGENT_ARN.replace(":", "%3A").replace("/", "%2F")
    return f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

class McpRequest(BaseModel):
    jsonrpc: str
    id: int
    method: str
    params: dict = {}

@app.options("/prod/api/mcp")
async def options_mcp():
    """Handle CORS preflight"""
    return {
        "message": "OK"
    }

@app.post("/prod/api/mcp")
async def proxy_mcp(request: McpRequest):
    """Proxy MCP requests to AgentCore with SigV4 signing"""
    try:
        # Get AWS credentials
        session = boto3.Session()
        credentials = session.get_credentials()
        
        mcp_url = get_mcp_url()
        request_body = json.dumps(request.dict())
        
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
        
        with urllib.request.urlopen(req, timeout=60) as response:
            response_data = response.read().decode('utf-8')
            print(f"Response from AgentCore: {response_data[:500]}")
            
            # Parse SSE format (event: message\ndata: {...})
            if response_data.startswith('event:'):
                lines = response_data.split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        json_data = line[6:]  # Remove 'data: ' prefix
                        result = json.loads(json_data)
                        break
            else:
                result = json.loads(response_data)
        
        return result
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "agentArn": AGENT_ARN,
        "region": REGION,
        "mcpUrl": get_mcp_url()
    }

# Lambda handler
handler = Mangum(app)
