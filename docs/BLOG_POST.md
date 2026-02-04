# Building an AI-Powered CloudFormation Generator with Amazon Bedrock AgentCore and MCP

## Introduction

Infrastructure as Code (IaC) has revolutionized how we deploy and manage cloud resources, but writing CloudFormation templates remains a time-consuming task that requires deep AWS expertise. What if you could simply describe your infrastructure needs in plain English and have an AI architect generate production-ready templates, complete with professional diagrams, cost analysis, and Well-Architected Framework reviews?

In this post, I'll show you how I built an AI-powered CloudFormation generator using Amazon Bedrock AgentCore Runtime, the Model Context Protocol (MCP), and Claude Sonnet 4.5. The solution transforms natural language prompts into complete infrastructure designs with:

- **Professional architecture diagrams** with official AWS icons
- **Validated CloudFormation templates** in YAML or JSON
- **Cost optimization analysis** with specific recommendations
- **Well-Architected Framework reviews** across all 6 pillars
- **One-click deployment** to AWS

## What is the Model Context Protocol (MCP)?

The Model Context Protocol is an open standard that enables AI models to securely interact with external tools and data sources. Think of it as a universal adapter that lets AI agents call functions, access databases, and integrate with APIs in a standardized way.

MCP servers expose "tools" - functions that AI models can discover and invoke. Each tool has:
- A clear name and description
- Typed parameters with validation
- Structured return values
- Built-in error handling

This makes it perfect for building AI agents that need to interact with AWS services, as we can expose CloudFormation operations, Bedrock model calls, and diagram generation as MCP tools.

## Why Amazon Bedrock AgentCore Runtime?

Amazon Bedrock AgentCore Runtime is a serverless platform specifically designed for hosting MCP servers in production. It provides:

- **Serverless auto-scaling** - No infrastructure to manage
- **Built-in IAM authentication** - Secure by default with AWS SigV4
- **Session management** - Automatic handling of stateful conversations
- **Observability** - CloudWatch Logs and X-Ray tracing out of the box
- **Container support** - Deploy custom dependencies like GraphViz
- **Cost-effective** - Pay only for what you use

Unlike traditional Lambda functions, AgentCore is optimized for long-running AI operations with extended timeouts (up to 10 minutes) and streaming responses.

## Solution Architecture

The solution consists of three main layers:

### 1. Frontend Layer (Web UI)
A modern, responsive web interface with:
- **3-panel layout**: Chat interface, architecture canvas, and artifact viewer
- **Real-time updates**: WebSocket connection for instant feedback
- **Auto-sequencing**: Automatically runs all 4 analysis tools in sequence
- **Professional rendering**: Markdown support, syntax highlighting, and image display

### 2. Backend Layer (API Gateway + Lambda)
- **WebSocket API**: Maintains persistent connections with no timeout limits
- **Lambda handler**: Processes requests asynchronously and signs AWS requests
- **SigV4 authentication**: Securely calls AgentCore Runtime with IAM credentials
- **Progress tracking**: Sends real-time status updates to the frontend

### 3. MCP Server Layer (AgentCore Runtime)
A containerized Python application running on AgentCore that exposes 7 MCP tools:

**1. generate_architecture_overview**
- Input: Natural language requirements
- Uses: Claude Sonnet 4.5 via Bedrock
- Output: Comprehensive architecture overview with ASCII diagrams, component breakdown, design decisions, and security considerations
- Time: 10-15 seconds

**2. build_cfn_template**
- Input: Natural language prompt
- Uses: Claude Sonnet 4.5 via Bedrock
- Output: Production-ready CloudFormation template (YAML/JSON)
- Time: 5-10 seconds

**3. generate_architecture_diagram**
- Input: CloudFormation template
- Uses: Python diagrams package + GraphViz
- Output: Professional PNG with official AWS service icons (base64-encoded)
- Time: 2-5 seconds

**4. validate_cfn_template**
- Input: CloudFormation template
- Uses: AWS CloudFormation ValidateTemplate API
- Output: Validation results + required capabilities
- Time: 1-2 seconds

**5. analyze_cost_optimization**
- Input: CloudFormation template or architecture overview
- Uses: Claude Sonnet 4.5 via Bedrock
- Output: Cost drivers, optimization recommendations, estimated savings
- Time: 5-10 seconds

**6. well_architected_review**
- Input: CloudFormation template or architecture overview
- Uses: Claude Sonnet 4.5 via Bedrock
- Output: 6-pillar review with specific recommendations
- Time: 10-15 seconds

**7. provision_cfn_stack**
- Input: Stack name + template
- Uses: AWS CloudFormation CreateStack/UpdateStack API
- Output: Stack ID + deployment status
- Time: 2-5 seconds

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                           │
│                    (AWS Console-style Web UI)                    │
│  • Natural language input                                        │
│  • 4 tabs: Architecture, Cost, Template, Review                  │
│  • Professional diagram display with AWS icons                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket (WSS)
                         │ No timeout limits
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              API Gateway (WebSocket API)                        │
│  • Protocol: WebSocket                                          │
│  • Routes: $connect, $default, $disconnect                      │
│  • Real-time bidirectional communication                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ Invokes
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              Lambda Function (WebSocket Handler)                 │
│  • Runtime: Python 3.11                                         │
│  • Timeout: 600 seconds (10 minutes)                            │
│  • Function: Async processing + AWS SigV4 signing               │
│  • Returns immediately, processes in background                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS + SigV4
                         │ IAM Authentication
                         │
┌────────────────────────▼────────────────────────────────────────┐
│           AgentCore Runtime (MCP Server Container)               │
│  • Protocol: MCP (Model Context Protocol)                       │
│  • Transport: Streamable HTTP                                   │
│  • Authentication: AWS IAM (SigV4)                              │
│  • Container: Python 3.13 + GraphViz                            │
│  • Observability: CloudWatch + X-Ray                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ 7 MCP Tools
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      AWS Services                                │
│  • Amazon Bedrock (Claude Sonnet 4.5)                           │
│  • AWS CloudFormation                                           │
│  • Amazon S3 (for artifacts)                                    │
└──────────────────────────────────────────────────────────────────┘
```

## How It Works: Step-by-Step

Let's walk through what happens when a user types "Create a serverless API with API Gateway, Lambda, and DynamoDB":

### Step 1: Architecture Overview Generation
The frontend sends the prompt to the Lambda backend via WebSocket. Lambda calls the `generate_architecture_overview` MCP tool, which:
1. Sends the prompt to Claude Sonnet 4.5 via Bedrock
2. Receives a comprehensive architecture overview with:
   - Executive summary
   - ASCII diagram with AWS service emojis
   - Component breakdown with rationale
   - Design decisions explained
   - Data flow description
   - Security considerations

### Step 2: CloudFormation Template Generation
The system automatically calls `build_cfn_template` with the same prompt:
1. Claude Sonnet 4.5 generates a production-ready CloudFormation template
2. Template includes all necessary resources (API Gateway, Lambda, DynamoDB)
3. Follows AWS best practices and naming conventions
4. Returns in YAML format (JSON also supported)

### Step 3: Professional Diagram Generation
The `generate_architecture_diagram` tool processes the CloudFormation template:
1. Parses the template to extract AWS resources
2. Maps resource types to official AWS service icons
3. Generates Python code using the `diagrams` package
4. Executes GraphViz to create a professional PNG
5. Base64-encodes the image for web display
6. Returns the diagram in ~3 seconds

### Step 4: Template Validation
The `validate_cfn_template` tool verifies the template:
1. Calls AWS CloudFormation ValidateTemplate API
2. Checks syntax, resource types, and property values
3. Returns required capabilities (e.g., CAPABILITY_IAM)
4. Identifies any errors before deployment

### Step 5: Well-Architected Review
The `well_architected_review` tool analyzes the architecture:
1. Evaluates against all 6 pillars:
   - Operational Excellence
   - Security
   - Reliability
   - Performance Efficiency
   - Cost Optimization
   - Sustainability
2. Provides specific recommendations for each pillar
3. References actual resources in the template
4. Assigns priority levels (High/Medium/Low)

### Step 6: Cost Analysis
The `analyze_cost_optimization` tool estimates costs:
1. Analyzes each resource in the template
2. Estimates monthly costs per service
3. Identifies cost drivers
4. Provides optimization recommendations
5. Shows estimated savings with specific dollar amounts

All of this happens automatically in sequence, with progress updates sent to the frontend via WebSocket. The entire process takes 30-45 seconds.

## Key Technical Decisions

### Why WebSocket Instead of HTTP?
Traditional HTTP APIs have timeout limits (typically 30 seconds for API Gateway). Since our AI operations can take 30-45 seconds for the full sequence, we needed a solution that:
- Supports long-running operations
- Provides real-time progress updates
- Maintains bidirectional communication
- Doesn't timeout

WebSocket connections stay open indefinitely, allowing the Lambda function to process requests asynchronously and send updates as each tool completes.

### Why AgentCore Instead of Lambda?
While we could run the MCP server directly in Lambda, AgentCore provides:
- **Container support**: We need GraphViz for diagram generation, which requires system packages
- **Extended timeouts**: Up to 10 minutes vs Lambda's 15-minute limit
- **Session management**: Automatic handling of stateful MCP sessions
- **Optimized for AI**: Built specifically for hosting AI agents and MCP servers
- **Better observability**: Integrated CloudWatch and X-Ray tracing

### Why MCP Protocol?
MCP provides a standardized way to expose tools to AI models:
- **Type safety**: Parameters are validated automatically
- **Discoverability**: AI models can list and understand available tools
- **Error handling**: Built-in error propagation and retry logic
- **Streaming support**: Can stream responses for long operations
- **Vendor neutral**: Works with any AI model or framework

### Security Architecture
The solution implements defense-in-depth security:

1. **No public endpoints**: Lambda function is not publicly accessible
2. **IAM authentication**: All AgentCore calls require SigV4 signed requests
3. **Credentials server-side**: Browser never sees AWS credentials
4. **Least privilege**: Each component has minimal IAM permissions
5. **Encryption everywhere**: HTTPS for all communications, encrypted logs
6. **Audit trail**: CloudWatch Logs + X-Ray + CloudTrail

## Implementation Highlights

### MCP Server Code Structure
The MCP server is built using FastMCP, a Python framework for building MCP servers:

```python
from mcp.server.fastmcp import FastMCP

# CRITICAL: stateless_http=True is required for AgentCore
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Expose ASGI app for AgentCore
app = mcp.streamable_http_app

@mcp.tool()
def build_cfn_template(prompt: str, format: str = "yaml") -> dict:
    """Generate CloudFormation template from natural language"""
    bedrock = get_bedrock_client()
    
    response = bedrock.invoke_model(
        modelId='anthropic.claude-sonnet-4-5-20250929-v1:0',
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 4096,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': prompt}]
        })
    )
    
    template = parse_response(response)
    return {'success': True, 'template': template}
```

Key points:
- `stateless_http=True` is required for AgentCore compatibility
- Tools are decorated with `@mcp.tool()` for automatic registration
- Return values must be JSON-serializable dictionaries
- Error handling is built into the MCP protocol

### Diagram Generation with GraphViz
The diagram generation tool uses the Python `diagrams` package:

```python
def generate_diagram_code(resources: list) -> str:
    """Generate Python code for AWS architecture diagram"""
    code = """
from diagrams import Diagram
from diagrams.aws.compute import Lambda
from diagrams.aws.network import APIGateway
from diagrams.aws.database import Dynamodb

with Diagram("AWS Architecture", show=False):
    api = APIGateway("API Gateway")
    fn = Lambda("Lambda Function")
    db = Dynamodb("DynamoDB Table")
    
    api >> fn >> db
"""
    return code
```

The generated code is executed in a temporary directory, producing a professional PNG with official AWS icons.

### WebSocket Handler with Async Processing
The Lambda function handles WebSocket connections and processes MCP calls asynchronously:

```python
def lambda_handler(event, context):
    route_key = event['requestContext']['routeKey']
    
    if route_key == '$default':
        # Acknowledge immediately
        send_message(connection_id, {'type': 'acknowledged'})
        
        # Invoke self asynchronously for long-running operation
        lambda_client.invoke(
            FunctionName=context.function_name,
            InvocationType='Event',
            Payload=json.dumps({
                'async_processing': {
                    'tool': tool_name,
                    'arguments': args,
                    'connectionId': connection_id
                }
            })
        )
        
        return {'statusCode': 200}
```

This pattern allows the Lambda function to return immediately while processing continues in the background.

## Deployment Process

The solution is deployed using the AgentCore CLI and CloudFormation:

### 1. Deploy MCP Server to AgentCore
```bash
# Configure AgentCore
agentcore configure \
  -e mcp_server.py \
  --protocol MCP \
  --deployment-type container \
  --non-interactive

# Deploy to AWS
agentcore launch
```

This creates:
- ECR repository for the container image
- AgentCore Runtime with the MCP server
- IAM execution role with necessary permissions
- CloudWatch Log Groups for observability
- X-Ray tracing configuration

### 2. Deploy WebSocket Backend
```bash
# Deploy CloudFormation stack
aws cloudformation create-stack \
  --stack-name cfn-builder-websocket \
  --template-body file://websocket-infrastructure.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=AgentArn,ParameterValue=$AGENT_ARN
```

This creates:
- API Gateway WebSocket API
- Lambda function with WebSocket handler
- IAM role for Lambda with AgentCore permissions
- CloudWatch Log Groups

### 3. Deploy Frontend to Amplify
```bash
# Push to GitHub
git add .
git commit -m "Deploy frontend"
git push

# Amplify auto-deploys from GitHub
```

## Cost Analysis

For a typical usage pattern of ~1,000 requests per month:

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| AgentCore Runtime | $10-20 | Serverless, pay per invocation |
| Lambda (WebSocket) | $1 | Minimal compute time |
| API Gateway | $0.05 | WebSocket connections |
| Bedrock (Claude 4.5) | $20-40 | Based on token usage |
| Storage/Logs | $2 | CloudWatch + S3 |
| **Total** | **$35-65** | Scales with usage |

The solution is cost-effective because:
- AgentCore auto-scales to zero when not in use
- WebSocket connections are reused efficiently
- Bedrock charges only for tokens processed
- No always-on infrastructure

## Lessons Learned

### 1. MCP Protocol Requires Stateless Design
AgentCore requires `stateless_http=True` for MCP servers. This means:
- No in-memory state between requests
- Each tool call must be self-contained
- Session management is handled by AgentCore

### 2. GraphViz Needs Container Deployment
The diagram generation tool requires GraphViz system packages, which aren't available in standard Lambda environments. AgentCore's container support solved this perfectly.

### 3. WebSocket Enables Better UX
Real-time progress updates dramatically improve the user experience. Users can see:
- Which tool is currently running
- Progress percentage
- Intermediate results
- Error messages immediately

### 4. Claude Sonnet 4.5 Excels at Architecture
Claude Sonnet 4.5 consistently generates:
- Valid CloudFormation templates
- Thoughtful architecture decisions
- Specific, actionable recommendations
- Well-structured markdown output

### 5. Retry Logic is Essential
Bedrock can throttle requests during high usage. Implementing exponential backoff retry logic ensures reliability:

```python
def call_bedrock_with_retry(bedrock, model_id, body, max_retries=3):
    for attempt in range(max_retries):
        try:
            return bedrock.invoke_model(modelId=model_id, body=body)
        except ThrottlingException:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + (0.1 * attempt)
                time.sleep(wait_time)
                continue
            raise
```

## Future Enhancements

Potential improvements for the solution:

1. **Multi-region support**: Deploy to multiple AWS regions for lower latency
2. **Template versioning**: Store and compare template versions over time
3. **Terraform support**: Generate Terraform configurations in addition to CloudFormation
4. **Cost tracking**: Integrate with AWS Cost Explorer for actual cost data
5. **Deployment automation**: Automatically deploy templates after validation
6. **Collaboration features**: Share architectures with team members
7. **Template library**: Save and reuse common patterns
8. **Integration with CI/CD**: Trigger deployments from GitHub Actions

## Conclusion

Building an AI-powered CloudFormation generator with Amazon Bedrock AgentCore and MCP demonstrates the power of combining:
- **Generative AI** (Claude Sonnet 4.5) for intelligent template generation
- **Serverless infrastructure** (AgentCore) for scalable, cost-effective hosting
- **Standardized protocols** (MCP) for tool integration
- **Modern UX patterns** (WebSocket) for real-time feedback

The result is a solution that transforms infrastructure design from a time-consuming, expert-only task into a conversational experience accessible to developers of all skill levels.

The Model Context Protocol is emerging as a key standard for AI agent development, and Amazon Bedrock AgentCore Runtime provides the perfect platform for hosting MCP servers in production. Together, they enable developers to build sophisticated AI-powered tools without managing infrastructure.

## Resources

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [Source Code Repository](https://github.com/adhavle-aws/ict-mcp-server)

---

**About the Author**: This solution was built to demonstrate the capabilities of Amazon Bedrock AgentCore Runtime and the Model Context Protocol for building production-ready AI agents. The complete source code is available on GitHub.

**Try it yourself**: Deploy the solution in your AWS account and start generating CloudFormation templates from natural language in minutes!
