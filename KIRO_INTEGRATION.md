# Kiro/IDE Integration Guide

## Overview

Your CloudFormation MCP Server can be used in Kiro, Cursor, VS Code, and other IDEs that support MCP.

## Installation

### 1. Install the Client

```bash
# Clone the repository
git clone https://github.com/adhavle-aws/ict-mcp-server.git
cd ict-mcp-server/cfn-mcp-server

# Install dependencies
pip install -r requirements.txt

# Make client executable
chmod +x cfn_mcp_client.py

# Optional: Create symlink for easy access
sudo ln -s $(pwd)/cfn_mcp_client.py /usr/local/bin/cfn-mcp-client
```

### 2. Configure AWS Credentials

```bash
# Ensure AWS credentials are configured
aws configure

# Or use AWS SSO
aws sso login --profile your-profile
```

### 3. Add to Kiro

Edit `~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "cloudformation-builder": {
      "command": "python3",
      "args": ["/path/to/cfn-mcp-server/cfn_mcp_client.py"],
      "env": {
        "AWS_PROFILE": "default",
        "AWS_REGION": "us-east-1"
      },
      "disabled": false,
      "autoApprove": [
        "build_cfn_template",
        "generate_architecture_diagram",
        "validate_cfn_template",
        "analyze_cost_optimization",
        "well_architected_review"
      ]
    }
  }
}
```

### 4. Restart Kiro

The MCP server will be available in Kiro's MCP panel.

## Usage in Kiro

### Example Prompts

**Generate Infrastructure:**
```
Create a CloudFormation template for a serverless API with API Gateway, Lambda, and DynamoDB
```

**Generate Diagram:**
```
Generate an architecture diagram for this CloudFormation template:
[paste template]
```

**Validate Template:**
```
Validate this CloudFormation template:
[paste template]
```

**Cost Analysis:**
```
Analyze cost optimization opportunities for this template:
[paste template]
```

**Well-Architected Review:**
```
Perform a Well-Architected Framework review on this template:
[paste template]
```

## Available Tools

When configured, Kiro will have access to:

1. **build_cfn_template** - Generate CloudFormation from natural language
2. **generate_architecture_diagram** - Create professional PNG diagrams
3. **validate_cfn_template** - Validate templates via AWS API
4. **analyze_cost_optimization** - AI-powered cost analysis
5. **well_architected_review** - Well-Architected Framework review
6. **provision_cfn_stack** - Deploy stacks to AWS

## Configuration Options

### Custom Agent ARN

If you deploy your own instance:

```json
{
  "mcpServers": {
    "cloudformation-builder": {
      "command": "python3",
      "args": ["/path/to/cfn_mcp_client.py"],
      "env": {
        "AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/YOUR_AGENT",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

### AWS Profile

Use a specific AWS profile:

```json
{
  "env": {
    "AWS_PROFILE": "your-profile-name",
    "AWS_REGION": "us-east-1"
  }
}
```

### Auto-Approve Tools

Auto-approve specific tools to avoid confirmation prompts:

```json
{
  "autoApprove": [
    "build_cfn_template",
    "generate_architecture_diagram",
    "validate_cfn_template"
  ]
}
```

## Architecture

```
Kiro/IDE
    ↓ stdio
cfn_mcp_client.py (Local Proxy)
    ↓ HTTPS + SigV4
AgentCore Runtime (AWS)
    ↓
MCP Server (Container)
    ↓
6 Tools (including diagram generation)
```

## Benefits

✅ **Native IDE Integration** - Works in Kiro, Cursor, VS Code
✅ **AWS Authentication** - Uses your AWS credentials
✅ **Zero Server Management** - Serverless backend
✅ **Professional Diagrams** - Official AWS icons
✅ **AI-Powered** - Claude Sonnet 3.5 via Bedrock
✅ **Secure** - IAM authentication, no API keys

## Troubleshooting

### "AWS credentials not found"

```bash
# Configure AWS
aws configure

# Or use SSO
aws sso login
```

### "Connection refused"

Check that the Agent ARN is correct in `cfn_mcp_client.py`:

```python
AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-VpWbdyCLTH"
```

### "Tool not found"

Restart Kiro to reload MCP servers:
- Command Palette → "Reload Window"
- Or restart Kiro completely

### "Permission denied"

Ensure your AWS credentials have permissions for:
- `bedrock-agentcore:*`
- `bedrock:InvokeModel`
- `cloudformation:*`

## Example Kiro Session

```
You: Create a 3-tier web application with VPC, ALB, ECS, and RDS

Kiro: I'll use the CloudFormation Builder MCP server to generate that.
[Calls build_cfn_template tool]

Here's the CloudFormation template:
[Shows template]

Would you like me to generate an architecture diagram?

You: Yes

Kiro: [Calls generate_architecture_diagram tool]
Here's the professional architecture diagram:
[Shows PNG diagram with AWS icons]

Would you like a cost analysis or Well-Architected review?
```

## Alternative: Direct Python Usage

If you don't want IDE integration, use the Python client directly:

```python
from mcp_client_remote import main

# This will connect to the deployed MCP server
asyncio.run(main())
```

## Summary

Your CloudFormation MCP Server can be integrated into any MCP-compatible IDE with a simple configuration. The `cfn_mcp_client.py` acts as a local proxy that handles AWS authentication and connects to your deployed AgentCore Runtime.

**Configuration**: Add to `~/.kiro/settings/mcp.json`
**Usage**: Natural language prompts in Kiro
**Result**: Professional CloudFormation templates and diagrams
