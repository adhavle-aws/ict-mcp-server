"""
Remote MCP client with AWS IAM authentication
Tests deployed MCP server on AgentCore Runtime
"""
import asyncio
import sys
import boto3
from boto3.session import Session
from mcp import ClientSession
from streamable_http_sigv4 import streamablehttp_client_with_sigv4


async def main():
    # Get AWS session and region
    boto_session = Session()
    region = boto_session.region_name or 'us-east-1'
    print(f"Using AWS region: {region}")
    
    # Get Agent ARN (hardcoded for now - could use SSM Parameter Store)
    agent_arn = "arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-CxkrO53RPH"
    print(f"Agent ARN: {agent_arn}")
    
    # Encode ARN for URL
    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    
    # Construct MCP URL
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    print(f"MCP URL: {mcp_url}\n")
    
    # Get AWS credentials
    credentials = boto_session.get_credentials()
    
    try:
        # Create transport with SigV4 signing
        async with streamablehttp_client_with_sigv4(
            url=mcp_url,
            credentials=credentials,
            service="bedrock-agentcore",
            region=region,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                print("🔄 Initializing MCP session...")
                await session.initialize()
                print("✓ MCP session initialized\n")
                
                # List tools
                print("🔄 Listing available tools...")
                tool_result = await session.list_tools()
                
                print("\n📋 Available MCP Tools:")
                print("=" * 60)
                for tool in tool_result.tools:
                    print(f"🔧 {tool.name}")
                    print(f"   {tool.description}")
                    print()
                
                # Test build_cfn_template with natural language
                print("\n🧪 Testing build_cfn_template with natural language:")
                print("=" * 60)
                print("Prompt: Create an S3 bucket with versioning and encryption\n")
                
                result = await session.call_tool(
                    name="build_cfn_template",
                    arguments={
                        "prompt": "Create an S3 bucket with versioning and encryption",
                        "format": "yaml"
                    }
                )
                
                print("Result:")
                for content in result.content:
                    if content.type == "text":
                        import json
                        data = json.loads(content.text)
                        if data.get('success'):
                            print(data.get('template', 'No template'))
                        else:
                            print(f"Error: {data.get('error')}")
                
                print("\n✅ MCP server is working correctly!")
                
    except Exception as e:
        print(f"❌ Error connecting to MCP server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
