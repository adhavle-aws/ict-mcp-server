# CloudFormation MCP Server

AI-powered infrastructure design platform that transforms natural language into production-ready CloudFormation templates with professional architecture diagrams.

## Features

- 🏗️ **Natural Language to CloudFormation** - Generate templates from plain English
- 📊 **Professional Architecture Diagrams** - Auto-generate visual diagrams with AWS official icons
- ✅ **Template Validation** - Validate against AWS CloudFormation API
- 💰 **Cost Optimization** - AI-powered cost analysis and recommendations
- 🏛️ **Well-Architected Review** - Automated 6-pillar framework review
- 🚀 **Stack Provisioning** - Deploy validated templates directly to AWS

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                           │
│                    (AWS Console-style Web UI)                    │
│  • Natural language input                                        │
│  • 4 tabs: Architecture (Canvas/Resources), Cost, Template,      │
│    Well-Architected Review                                       │
│  • Professional diagram display with AWS icons                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket (WSS)
                         │ No timeout limits
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              API Gateway (WebSocket API)                        │
│  • Endpoint: z832i481e5.execute-api.us-east-1.amazonaws.com     │
│  • Protocol: WebSocket                                          │
│  • Routes: $connect, $default, $disconnect                      │
│  • Real-time bidirectional communication                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ Invokes
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              Lambda Function (WebSocket Handler)                 │
│  • Name: cfn-builder-websocket                                  │
│  • Runtime: Python 3.11                                         │
│  • Timeout: 600 seconds (10 minutes)                            │
│  • Memory: 512 MB                                               │
│  • Security: NOT publicly accessible                            │
│  • Function: Async processing + AWS SigV4 signing               │
│  • Returns immediately, processes in background thread          │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS + SigV4
                         │ IAM Authentication
                         │
┌────────────────────────▼────────────────────────────────────────┐
│           AgentCore Runtime (MCP Server Container)               │
│  • ARN: mcp_server-VpWbdyCLTH                                   │
│  • Protocol: MCP (Model Context Protocol)                       │
│  • Transport: Streamable HTTP                                   │
│  • Authentication: AWS IAM (SigV4)                              │
│  • Container: Python 3.13 + GraphViz                            │
│  • Session Management: Automatic                                │
│  • Observability: CloudWatch + X-Ray                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ 6 MCP Tools
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    MCP Tools Layer                               │
│                                                                  │
│  1. build_cfn_template                                          │
│     • Input: Natural language prompt                            │
│     • Uses: Claude Sonnet 3.5 (Bedrock)                        │
│     • Output: CloudFormation YAML/JSON                          │
│     • Time: 5-10 seconds                                        │
│                                                                  │
│  2. generate_architecture_diagram ⭐ NEW                         │
│     • Input: CloudFormation template                            │
│     • Uses: Python diagrams + GraphViz                          │
│     • Output: Professional PNG with AWS icons (base64)          │
│     • Time: 2-5 seconds                                         │
│                                                                  │
│  3. validate_cfn_template                                       │
│     • Input: CloudFormation template                            │
│     • Uses: AWS CloudFormation ValidateTemplate API             │
│     • Output: Validation results + required capabilities        │
│     • Time: 1-2 seconds                                         │
│                                                                  │
│  4. analyze_cost_optimization                                   │
│     • Input: CloudFormation template                            │
│     • Uses: Claude Sonnet 3.5 (Bedrock)                        │
│     • Output: Cost drivers + optimization recommendations       │
│     • Time: 5-10 seconds                                        │
│                                                                  │
│  5. well_architected_review                                     │
│     • Input: CloudFormation template                            │
│     • Uses: Claude Sonnet 3.5 (Bedrock)                        │
│     • Output: 6-pillar review + recommendations                 │
│     • Time: 10-15 seconds                                       │
│                                                                  │
│  6. provision_cfn_stack                                         │
│     • Input: Stack name + template                              │
│     • Uses: AWS CloudFormation CreateStack/UpdateStack          │
│     • Output: Stack ID + status                                 │
│     • Time: 2-5 seconds                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ boto3 SDK
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      AWS Services                                │
│  • Amazon Bedrock (Claude Sonnet 3.5)                           │
│  • AWS CloudFormation                                           │
└──────────────────────────────────────────────────────────────────┘
```

## Key Architecture Benefits

### WebSocket Design
- ✅ **No Timeout Limits** - Browser to Lambda connection stays open
- ✅ **Real-time Updates** - Progress messages during long operations
- ✅ **Bidirectional** - Server can push updates to client
- ✅ **Async Processing** - Lambda returns immediately, processes in background

### Security Model
- ✅ **Lambda Not Public** - No function URL, only API Gateway can invoke
- ✅ **IAM Authentication** - AgentCore requires SigV4 signed requests
- ✅ **Credentials Server-Side** - Browser never sees AWS credentials
- ✅ **Least Privilege** - Minimal IAM permissions throughout

### Scalability
- ✅ **AgentCore Auto-Scales** - Serverless container platform
- ✅ **Lambda Concurrent** - Handles multiple connections
- ✅ **WebSocket Persistent** - Efficient connection reuse
- ✅ **No Cold Starts** - AgentCore keeps containers warm

## Quick Start

### Prerequisites

- AWS Account with credentials configured
- Python 3.10+
- GraphViz (for local diagram generation)

### Installation

```bash
# Install GraphViz
brew install graphviz  # macOS
sudo apt-get install graphviz  # Linux

# Install Python dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
# Start MCP server
python mcp_server.py

# Test with client
python mcp_client.py
```


## Deployment

All AWS deployments use the **`aws-gaurav`** profile. The app runs on **Amplify**; pushing to git triggers a frontend deploy.

### Deploy AgentCore (MCP server)

From the project root:

```bash
./deploy-agentcore.sh   # Uses profile aws-gaurav
```

### Deploy frontend (Amplify)

Push to your connected Git repository; Amplify builds and deploys automatically (see `amplify.yml`).

```bash
git add .
git commit -m "Your changes"
git push
```

### Optional: deploy WebSocket backend (Lambda + API Gateway)

If you use the WebSocket stack, run from project root (scripts use profile aws-gaurav):

```bash
./deploy-to-aws.sh   # or your CloudFormation deploy
```

## Deployment Status

### ✅ Deployed to AWS

- **Agent ARN**: `arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-VpWbdyCLTH`
- **WebSocket API**: `wss://197c9q4u8i.execute-api.us-east-1.amazonaws.com/prod`
- **Deployment Type**: Container (with GraphViz)
- **Region**: us-east-1
- **Profile**: aws-gaurav for AgentCore and CLI deployments

### Available Tools

All 6 tools are live and functional:

1. ✅ `build_cfn_template` - Generate CloudFormation from natural language
2. ✅ `generate_architecture_diagram` - Create professional PNG diagrams ⭐ NEW
3. ✅ `validate_cfn_template` - Validate templates via AWS API
4. ✅ `analyze_cost_optimization` - AI-powered cost analysis
5. ✅ `well_architected_review` - Well-Architected Framework review
6. ✅ `provision_cfn_stack` - Deploy stacks to AWS

## Usage

### Via UI

```bash
# Start backend (local testing)
cd ui/backend_python
python server.py

# Open frontend
open ui/frontend/index.html

# Enter prompt:
"Create a serverless API with API Gateway, Lambda, and DynamoDB"

# Click Generate → View professional diagram in Canvas tab
```

### Via MCP Client

```python
import asyncio
from mcp import ClientSession
from streamable_http_sigv4 import streamablehttp_client_with_sigv4

async def main():
    agent_arn = "arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-VpWbdyCLTH"
    region = "us-east-1"
    
    # Encode ARN
    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    
    async with create_streamable_http_transport_sigv4(
        mcp_url, "bedrock-agentcore", region
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Generate template
            result = await session.call_tool(
                "build_cfn_template",
                {"prompt": "Create a serverless API", "format": "yaml"}
            )
            
            print(result)

asyncio.run(main())
```

### Via agentcore CLI

```bash
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create an S3 bucket with versioning",
      "format": "yaml"
    }
  }
}'
```


## Professional Diagram Generation ⭐ NEW

### How It Works

```
User Prompt
    ↓
build_cfn_template() → CloudFormation Template
    ↓
generate_architecture_diagram(template)
    ↓
1. Parse CloudFormation (YAML/JSON)
2. Extract AWS resources
3. Generate Python diagrams code
4. Execute with GraphViz
5. Create PNG with official AWS icons
6. Base64 encode for web display
    ↓
Professional Architecture Diagram
```

### Supported AWS Services (20+)

- **Compute**: Lambda, EC2, ECS
- **Network**: API Gateway, ALB, CloudFront, Route53
- **Database**: DynamoDB, RDS, ElastiCache
- **Storage**: S3
- **Security**: Cognito, IAM
- **Integration**: SNS, SQS, Step Functions, EventBridge
- **Analytics**: Kinesis

### Example Output

For a serverless API with API Gateway, Lambda, and DynamoDB:

- ✅ Professional PNG diagram
- ✅ Official AWS service icons
- ✅ Automatic layout with connections
- ✅ Base64 encoded (web-ready)
- ✅ 2-5 second generation time

## Repository Structure

```
cfn-mcp-server/
├── mcp_server.py              # MCP server with 6 tools
├── mcp_client.py              # Local test client
├── mcp_client_remote.py       # Remote client with IAM auth
├── streamable_http_sigv4.py   # SigV4 helper
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container with GraphViz
├── .bedrock_agentcore.yaml    # AgentCore config
├── deploy/
│   ├── infrastructure.yaml    # Backend CloudFormation
│   ├── websocket-infrastructure.yaml
│   └── lambda_backend/
│       ├── handler.py         # FastAPI handler
│       └── requirements.txt
├── ui/
│   ├── frontend/
│   │   └── index.html         # Web UI
│   └── backend_python/
│       └── server.py          # Local dev server
├── tests/
│   ├── test_diagram.py        # Diagram generation test
│   └── test_nl_prompts.sh     # Integration tests
└── docs/                      # Documentation
```

## Deployment

### Deploy MCP Server

```bash
# Configure
agentcore configure -e mcp_server.py --protocol MCP --deployment-type container

# Deploy
agentcore launch

# Test
agentcore invoke '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Deploy Backend (WebSocket)

```bash
./deploy-to-aws.sh
```

### Deploy Frontend (Amplify)

1. Push to GitHub (already done)
2. Go to AWS Amplify Console
3. Connect repository: `adhavle-aws/ict-mcp-server`
4. Deploy automatically


## Monitoring

### CloudWatch Logs

```bash
# MCP Server
aws logs tail /aws/bedrock-agentcore/runtimes/mcp_server-VpWbdyCLTH-DEFAULT \
  --log-stream-name-prefix "2026/01/30/[runtime-logs]" --follow

# Lambda Backend
aws logs tail /aws/lambda/cfn-builder-websocket --follow
```

### GenAI Observability Dashboard

https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#gen-ai-observability/agent-core

### X-Ray Tracing

- ✅ Enabled for all tool invocations
- ✅ Track latency and errors
- ✅ View in AWS X-Ray console

## Security

- ✅ **IAM Authentication** - SigV4 signed requests
- ✅ **No Public Endpoints** - Lambda not publicly accessible
- ✅ **Least Privilege** - Minimal IAM permissions
- ✅ **Encryption** - HTTPS everywhere, encrypted logs
- ✅ **Audit Trail** - CloudWatch + X-Ray + CloudTrail

## Cost Estimate

For 10,000 requests/month:

- AgentCore Runtime: ~$5-10
- Lambda: ~$1
- API Gateway: ~$0.04
- Bedrock (Claude): ~$15-30
- **Total**: ~$20-40/month

## Documentation

- `DEPLOYMENT_SUCCESS.md` - Deployment details
- `DIAGRAM_INTEGRATION.md` - Diagram feature guide
- `QUICK_START_DIAGRAMS.md` - Quick reference
- `.kiro/steering/MCP Server.md` - Development guide

## Support

For issues or questions:
- Check CloudWatch logs
- Verify GraphViz: `dot -V`
- Test locally first: `python mcp_client.py`
- Review documentation in `docs/`

## License

MIT

---

**Status**: ✅ Deployed and operational with professional diagram generation
