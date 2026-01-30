# mcp_client.py
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    mcp_url = "http://localhost:8000/mcp"
    headers = {}

    async with streamablehttp_client(mcp_url, headers, timeout=120, terminate_on_close=False) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # List tools
            tool_result = await session.list_tools()
            print("Available tools:")
            for tool in tool_result.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Test build_cfn_template with natural language
            print("\nTesting build_cfn_template with natural language...")
            result = await session.call_tool("build_cfn_template", {
                "prompt": "Create an S3 bucket with versioning enabled and encryption",
                "format": "yaml"
            })
            
            print("\nResult:")
            for content in result.content:
                if content.type == "text":
                    print(content.text)

if __name__ == "__main__":
    asyncio.run(main())
