#!/usr/bin/env python3
"""
Test script for diagram generation
"""

import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_diagram():
    mcp_url = "http://localhost:8000/mcp"
    headers = {}
    
    print("🔗 Connecting to MCP server...")
    
    async with streamablehttp_client(mcp_url, headers, timeout=120, terminate_on_close=False) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            print("✅ Connected!")
            print("\n📋 Available tools:")
            
            # List tools
            tool_result = await session.list_tools()
            for tool in tool_result.tools:
                print(f"  - {tool.name}: {tool.description[:80]}...")
            
            # Test template generation
            print("\n🏗️  Generating CloudFormation template...")
            template_result = await session.call_tool(
                "build_cfn_template",
                {
                    "prompt": "Create a simple serverless API with API Gateway, Lambda, and DynamoDB",
                    "format": "yaml"
                }
            )
            
            template = None
            for content in template_result.content:
                if content.type == "text":
                    import json
                    data = json.loads(content.text)
                    if data.get('success'):
                        template = data['template']
                        print("✅ Template generated!")
                        print(f"   Length: {len(template)} characters")
            
            if not template:
                print("❌ Failed to generate template")
                return
            
            print("\n✅ Test complete (template generation only; diagram tool removed).")

if __name__ == "__main__":
    asyncio.run(test_diagram())
