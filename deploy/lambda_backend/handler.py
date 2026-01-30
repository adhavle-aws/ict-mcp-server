"""
Lambda handler for CloudFormation Builder Backend
Uses FastAPI with Mangum adapter for Lambda
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum
import boto3
import os
import sys
import json

# Add parent directory to import streamable_http_sigv4
sys.path.insert(0, os.path.dirname(__file__))

from streamable_http_sigv4 import streamablehttp_client_with_sigv4
from mcp import ClientSession

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

@app.post("/prod/api/mcp")
async def proxy_mcp(request: McpRequest):
    """Proxy MCP requests to AgentCore with SigV4 signing"""
    try:
        # Get AWS credentials
        session = boto3.Session()
        credentials = session.get_credentials()
        
        mcp_url = get_mcp_url()
        
        # Connect with SigV4
        async with streamablehttp_client_with_sigv4(
            url=mcp_url,
            credentials=credentials,
            service="bedrock-agentcore",
            region=REGION,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()
                
                # Route based on method
                if request.method == "tools/list":
                    result = await mcp_session.list_tools()
                    return {
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "result": {
                            "tools": [
                                {
                                    "name": tool.name,
                                    "description": tool.description
                                }
                                for tool in result.tools
                            ]
                        }
                    }
                
                elif request.method == "tools/call":
                    tool_name = request.params.get("name")
                    arguments = request.params.get("arguments", {})
                    
                    result = await mcp_session.call_tool(tool_name, arguments)
                    
                    # Extract text from result
                    content = []
                    for item in result.content:
                        if item.type == "text":
                            content.append({
                                "type": "text",
                                "text": item.text
                            })
                    
                    return {
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "result": {
                            "content": content,
                            "isError": False
                        }
                    }
                
                else:
                    raise HTTPException(status_code=400, detail=f"Unknown method: {request.method}")
    
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
