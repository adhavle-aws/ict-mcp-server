#!/usr/bin/env python3
"""
CloudFormation MCP Client - CLI wrapper for Kiro/IDE integration

Usage:
    cfn-mcp-client

This acts as an MCP stdio server that proxies to the deployed AgentCore Runtime.
"""
import sys
import json
import asyncio
import boto3
from mcp import ClientSession, StdioServerParameters
from mcp.server import Server
from mcp.server.stdio import stdio_server
from streamable_http_sigv4 import streamablehttp_client_with_sigv4

# Configuration
AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-VpWbdyCLTH"
REGION = "us-east-1"

def get_mcp_url():
    """Get MCP endpoint URL"""
    encoded_arn = AGENT_ARN.replace(":", "%3A").replace("/", "%2F")
    return f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

def create_transport():
    """Create streamable HTTP transport with SigV4 auth"""
    session = boto3.Session()
    credentials = session.get_credentials()
    
    return streamablehttp_client_with_sigv4(
        url=get_mcp_url(),
        credentials=credentials,
        service="bedrock-agentcore",
        region=REGION,
    )

# Create MCP server that proxies to AgentCore
server = Server("cfn-mcp-client")

# Store remote session
remote_session = None

async def get_remote_session():
    """Get or create remote MCP session"""
    global remote_session
    
    if remote_session is None:
        transport = create_transport()
        read_stream, write_stream, _ = await transport.__aenter__()
        remote_session = ClientSession(read_stream, write_stream)
        await remote_session.__aenter__()
        await remote_session.initialize()
    
    return remote_session

@server.list_tools()
async def list_tools():
    """List available tools from remote MCP server"""
    session = await get_remote_session()
    result = await session.list_tools()
    return result.tools

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Call tool on remote MCP server"""
    session = await get_remote_session()
    result = await session.call_tool(name, arguments)
    return result.content

async def main():
    """Run MCP server over stdio"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
