# CloudFormation MCP Server with Claude

MCP server that generates CloudFormation templates from natural language using Claude.

## Architecture

```
Natural Language Prompt → MCP Server → Claude (Bedrock) → CloudFormation Template
```

## The 3 Tools

1. **build_cfn_template** - Generate CloudFormation from natural language (uses Claude)
2. **validate_cfn_template** - Validate templates via AWS API
3. **provision_cfn_stack** - Create/update stacks

## Deployed

**ARN**: `arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-CxkrO53RPH`

## Test with Natural Language

```bash
# Example 1: S3 Bucket
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create an S3 bucket with versioning and encryption",
      "format": "yaml"
    }
  }
}'

# Example 2: Lambda Function
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create a Lambda function with Python 3.11 runtime",
      "format": "yaml"
    }
  }
}'

# Example 3: VPC
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create a VPC with public and private subnets",
      "format": "yaml"
    }
  }
}'
```

## Run Test Suite

```bash
./test_nl_prompts.sh
```

## Local Development

```bash
# Start server
python3 mcp_server.py

# Test
python3 mcp_client.py
```

## Files

- `mcp_server.py` - MCP server with Claude integration
- `mcp_client.py` - Local test client
- `requirements.txt` - Dependencies
- `test_nl_prompts.sh` - Test suite

Your CloudFormation generator is ready! 🚀
