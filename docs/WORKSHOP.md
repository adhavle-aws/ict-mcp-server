# Workshop: Building AI-Powered Infrastructure Tools with Kiro, Amazon Bedrock AgentCore, and MCP

## Workshop Overview

**Level**: 300 (Advanced)  
**Duration**: 2-3 hours  
**Cost**: ~$5-10 for workshop resources (remember to clean up!)

In this hands-on workshop, you'll learn how to build an AI-powered CloudFormation generator using Kiro AI IDE, Amazon Bedrock AgentCore Runtime, and the Model Context Protocol (MCP). You'll experience how Kiro's AI-assisted development features—including steering files, powers, and specs—accelerate the development of complex AI agent applications.

### What You'll Build

An end-to-end AI infrastructure assistant that:
- Generates CloudFormation templates from natural language
- Creates professional architecture diagrams with AWS icons
- Performs Well-Architected Framework reviews
- Analyzes cost optimization opportunities
- Validates and deploys templates to AWS

### What You'll Learn

- How to use Kiro AI IDE for AI agent development
- Building MCP servers with FastMCP
- Deploying to Amazon Bedrock AgentCore Runtime
- Integrating Claude Sonnet 4.5 via Bedrock
- Creating WebSocket backends for real-time AI interactions
- Using Kiro's steering files for project-specific guidance
- Leveraging Kiro Powers for AWS integration

### Prerequisites

**Required:**
- AWS Account with administrator access
- AWS CLI configured with credentials
- Python 3.10 or later
- Node.js 18 or later (for frontend)
- Git installed
- Kiro AI IDE installed ([download here](https://kiro.dev))

**Recommended:**
- Basic understanding of AWS services (Lambda, API Gateway, CloudFormation)
- Familiarity with Python
- Experience with AI/LLM concepts

**AWS Services Used:**
- Amazon Bedrock (Claude Sonnet 4.5)
- Amazon Bedrock AgentCore Runtime
- AWS Lambda
- Amazon API Gateway (WebSocket)
- AWS CloudFormation
- Amazon S3
- Amazon CloudWatch
- AWS X-Ray

## Module 0: Workshop Setup (15 minutes)

### Step 1: Install Kiro AI IDE

1. Download Kiro from [kiro.dev](https://kiro.dev)
2. Install and launch Kiro
3. Sign in or create an account

### Step 2: Configure AWS Credentials

```bash
# Configure AWS CLI
aws configure

# Verify credentials
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDAI...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-user"
}
```

### Step 3: Install AgentCore CLI

```bash
# Install AgentCore CLI
pip install bedrock-agentcore-starter-toolkit

# Verify installation
agentcore --version
```

### Step 4: Enable Bedrock Model Access

1. Go to AWS Console → Amazon Bedrock
2. Navigate to "Model access" in the left sidebar
3. Click "Manage model access"
4. Enable "Claude Sonnet 4.5" (anthropic.claude-sonnet-4-5-20250929-v1:0)
5. Click "Save changes"

Wait 2-3 minutes for access to be granted.

### Step 5: Create Workshop Directory

```bash
# Create project directory
mkdir cfn-mcp-workshop
cd cfn-mcp-workshop

# Open in Kiro
kiro .
```

## Module 1: Understanding Kiro's AI-Assisted Development (20 minutes)

### What is Kiro?

Kiro is an AI-powered IDE that accelerates development through:
- **AI Chat**: Context-aware coding assistant
- **Steering Files**: Project-specific AI guidance
- **Powers**: Pre-built integrations (AWS, MCP, etc.)
- **Specs**: Structured feature development workflow
- **Autopilot Mode**: Autonomous code generation

### Step 1: Explore Kiro's Interface

1. Open Kiro with your workshop directory
2. Notice the key panels:
   - **Editor**: Code editing with AI assistance
   - **Chat**: AI assistant for questions and tasks
   - **File Explorer**: Project navigation
   - **Terminal**: Integrated command line

### Step 2: Try Kiro Chat

In the Kiro chat panel, try:

```
Create a Python file called hello.py that prints "Hello from Kiro!"
```

Watch as Kiro:
1. Creates the file
2. Writes the code
3. Explains what it did

### Step 3: Understanding Steering Files

Steering files provide project-specific guidance to Kiro's AI. Let's create one:

```
Create a steering file for MCP server development
```

Kiro will create `.kiro/steering/MCP Server.md` with guidance on:
- MCP protocol requirements
- AgentCore deployment patterns
- Best practices for tool development

**Key Concept**: Steering files are automatically included in Kiro's context, making the AI aware of your project's specific requirements and patterns.

### Step 4: Discover Kiro Powers

Powers are pre-built integrations that extend Kiro's capabilities.

In Kiro chat:
```
List available powers
```

You'll see powers for:
- AWS services (Bedrock, AgentCore, etc.)
- Development tools
- Documentation access

**For this workshop**, we'll use:
- **aws-agentcore**: Deploy and manage MCP servers
- **strands** (optional): Advanced agent orchestration

## Module 2: Building Your First MCP Server (30 minutes)

### What is MCP?

The Model Context Protocol (MCP) is an open standard for connecting AI models to external tools and data sources. MCP servers expose "tools" that AI models can discover and invoke.

### Step 1: Create Project Structure

In Kiro chat:
```
Create a Python project structure for an MCP server with:
- mcp_server.py (main server file)
- requirements.txt (dependencies)
- README.md (documentation)
```

### Step 2: Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install mcp boto3 pyyaml
```

### Step 3: Build a Simple MCP Tool

In Kiro chat:
```
Create an MCP server in mcp_server.py with a tool called 'hello_world' that takes a name parameter and returns a greeting. Use FastMCP and make it compatible with AgentCore (stateless_http=True).
```

Kiro will generate something like:

```python
from mcp.server.fastmcp import FastMCP

# CRITICAL: stateless_http=True required for AgentCore
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Expose ASGI app for AgentCore
app = mcp.streamable_http_app

@mcp.tool()
def hello_world(name: str) -> dict:
    """Say hello to someone"""
    return {
        'success': True,
        'message': f'Hello, {name}! Welcome to MCP.'
    }

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### Step 4: Test Locally

```bash
# Terminal 1: Start MCP server
python mcp_server.py
```

The server runs on `http://localhost:8000/mcp`

In a new terminal:
```bash
# Terminal 2: Test with curl
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

You should see your `hello_world` tool listed!

### Step 5: Understanding MCP Tool Structure

Ask Kiro to explain:
```
Explain the MCP tool structure in mcp_server.py
```

Key points:
- `@mcp.tool()` decorator registers functions as tools
- Type hints define parameter types
- Return values must be JSON-serializable
- `stateless_http=True` is required for AgentCore

## Module 3: Adding CloudFormation Generation (40 minutes)

### Step 1: Add Bedrock Integration

In Kiro chat:
```
Add a tool to mcp_server.py called 'build_cfn_template' that:
1. Takes a prompt parameter (natural language description)
2. Calls Claude Sonnet 4.5 via Bedrock
3. Returns a CloudFormation template in YAML format
4. Includes proper error handling
```

Kiro will add the necessary imports and implement the tool.

### Step 2: Add Template Validation

```
Add a tool called 'validate_cfn_template' that:
1. Takes a template_body parameter
2. Calls AWS CloudFormation ValidateTemplate API
3. Returns validation results and required capabilities
```

### Step 3: Test the New Tools

Update your test script:

```bash
# Test template generation
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "build_cfn_template",
      "arguments": {
        "prompt": "Create an S3 bucket with versioning enabled"
      }
    }
  }'
```

### Step 4: Add Architecture Overview Tool

```
Add a tool called 'generate_architecture_overview' that:
1. Takes a prompt parameter
2. Uses Claude Sonnet 4.5 to create a comprehensive architecture overview
3. Returns markdown with:
   - Executive summary
   - ASCII diagram with AWS service emojis
   - Component breakdown with rationale
   - Design decisions
   - Security considerations
```

### Step 5: Understanding Prompt Engineering

Ask Kiro:
```
Show me the system prompt used in build_cfn_template and explain why it's structured that way
```

Learn about:
- Clear instructions for the AI
- Output format specification
- Constraint definition
- Best practice enforcement

## Module 4: Deploying to AgentCore Runtime (30 minutes)

### Step 1: Configure AgentCore

In Kiro chat:
```
Help me configure AgentCore for deploying mcp_server.py
```

Or run manually:
```bash
agentcore configure \
  -e mcp_server.py \
  --protocol MCP \
  --non-interactive
```

This creates `.bedrock_agentcore.yaml` with your deployment configuration.

### Step 2: Review Configuration

Ask Kiro:
```
Explain the .bedrock_agentcore.yaml configuration
```

Key settings:
- `entrypoint`: Your MCP server file
- `protocol`: MCP
- `deployment_type`: container (for GraphViz support later)
- `aws.region`: Your AWS region

### Step 3: Deploy to AWS

```bash
# Deploy to AgentCore
agentcore launch
```

This process:
1. ✅ Creates Docker image
2. ✅ Pushes to ECR
3. ✅ Creates AgentCore Runtime
4. ✅ Sets up IAM roles
5. ✅ Configures CloudWatch logging
6. ✅ Returns Agent ARN

**Save your Agent ARN** - you'll need it later!

### Step 4: Test Deployed Server

```bash
# List tools
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}'

# Call a tool
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create a Lambda function with Python 3.11 runtime"
    }
  }
}'
```

### Step 5: Monitor with CloudWatch

```bash
# View logs
aws logs tail /aws/bedrock-agentcore/runtimes/YOUR_AGENT_ID-DEFAULT \
  --follow
```

## Module 5: Adding Professional Diagrams (30 minutes)

### Step 1: Install GraphViz

```bash
# macOS
brew install graphviz

# Ubuntu/Debian
sudo apt-get install graphviz

# Verify
dot -V
```

### Step 2: Add Diagram Generation Tool

In Kiro chat:
```
Add a tool called 'generate_architecture_diagram' that:
1. Takes a CloudFormation template as input
2. Parses the template to extract AWS resources
3. Uses the Python diagrams package to create a professional PNG
4. Returns the image as base64-encoded data
5. Includes proper error handling and timeout protection
```

### Step 3: Update Requirements

```
Update requirements.txt to include the diagrams package
```

### Step 4: Create Dockerfile for Container Deployment

```
Create a Dockerfile that:
1. Uses Python 3.13 base image
2. Installs GraphViz system packages
3. Installs Python dependencies
4. Copies the MCP server code
5. Exposes port 8000
6. Runs the MCP server
```

### Step 5: Redeploy with Container Support

```bash
# Update AgentCore configuration for container deployment
agentcore configure \
  -e mcp_server.py \
  --protocol MCP \
  --deployment-type container

# Redeploy
agentcore launch
```

### Step 6: Test Diagram Generation

```bash
# Generate a template and diagram
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "generate_architecture_diagram",
    "arguments": {
      "template_body": "YOUR_CLOUDFORMATION_TEMPLATE_HERE"
    }
  }
}'
```

## Module 6: Building the WebSocket Backend (25 minutes)

### Step 1: Create WebSocket Infrastructure

In Kiro chat:
```
Create a CloudFormation template called websocket-infrastructure.yaml that includes:
1. API Gateway WebSocket API
2. Lambda function for handling WebSocket connections
3. IAM roles with permissions for AgentCore
4. Routes for $connect, $default, and $disconnect
```

### Step 2: Implement Lambda Handler

```
Create a Lambda handler in deploy/lambda_websocket/handler.py that:
1. Handles WebSocket connections
2. Processes MCP tool calls asynchronously
3. Signs requests to AgentCore with SigV4
4. Sends progress updates to clients
5. Handles errors gracefully
```

### Step 3: Deploy WebSocket Stack

```bash
# Package Lambda code
cd deploy/lambda_websocket
zip -r lambda.zip handler.py
cd ../..

# Deploy CloudFormation stack
aws cloudformation create-stack \
  --stack-name cfn-builder-websocket \
  --template-body file://deploy/websocket-infrastructure.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=AgentArn,ParameterValue=YOUR_AGENT_ARN
```

### Step 4: Get WebSocket URL

```bash
# Get WebSocket URL from stack outputs
aws cloudformation describe-stacks \
  --stack-name cfn-builder-websocket \
  --query 'Stacks[0].Outputs[?OutputKey==`WebSocketUrl`].OutputValue' \
  --output text
```

Save this URL - you'll need it for the frontend!

## Module 7: Building the Frontend UI (25 minutes)

### Step 1: Create Frontend Structure

In Kiro chat:
```
Create a modern web UI in ui/frontend/chat.html with:
1. 3-panel layout (sidebar, chat, artifacts)
2. WebSocket connection to the backend
3. Real-time message display with markdown support
4. Professional AWS-style design
5. Auto-sequencing through all tools
```

### Step 2: Update WebSocket URL

```
Update the WebSocket URL in chat.html to use my deployed WebSocket API
```

Kiro will find and update the `WS_URL` constant.

### Step 3: Test Locally

```bash
# Open in browser
open ui/frontend/chat.html
```

Try typing:
```
Create a serverless API with API Gateway, Lambda, and DynamoDB
```

Watch as it:
1. ✅ Generates architecture overview
2. ✅ Creates CloudFormation template
3. ✅ Generates professional diagram
4. ✅ Runs Well-Architected review
5. ✅ Analyzes costs

### Step 4: Deploy to Amplify (Optional)

```bash
# Initialize git repository
git init
git add .
git commit -m "Initial commit"

# Push to GitHub
git remote add origin YOUR_GITHUB_REPO
git push -u origin main
```

Then in AWS Console:
1. Go to AWS Amplify
2. Click "New app" → "Host web app"
3. Connect your GitHub repository
4. Deploy automatically

## Module 8: Using Kiro Specs for Feature Development (20 minutes)

### What are Specs?

Specs are Kiro's structured approach to building features:
1. **Requirements**: Define what you want to build
2. **Design**: Plan the implementation
3. **Tasks**: Break down into actionable steps
4. **Implementation**: Let Kiro execute the tasks

### Step 1: Create a Spec

In Kiro chat:
```
Create a spec for adding cost optimization analysis to our MCP server
```

Kiro will create a spec file in `.kiro/specs/` with:
- Feature description
- Requirements
- Design considerations
- Implementation tasks

### Step 2: Review and Refine

```
Review the cost optimization spec and add a requirement for specific dollar amount estimates
```

### Step 3: Execute the Spec

```
Implement the cost optimization spec
```

Kiro will:
1. Read the spec
2. Create the necessary code
3. Update documentation
4. Run tests (if specified)

### Step 4: Verify Implementation

```bash
# Test the new tool
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "analyze_cost_optimization",
    "arguments": {
      "template_body": "YOUR_TEMPLATE_HERE"
    }
  }
}'
```

## Module 9: Advanced Features with Kiro Powers (15 minutes)

### Step 1: Activate AWS AgentCore Power

In Kiro:
```
Activate the aws-agentcore power
```

This gives Kiro direct access to AgentCore APIs for:
- Listing agents
- Viewing logs
- Managing deployments
- Monitoring performance

### Step 2: Use Power Tools

```
Use the agentcore power to show me the status of my deployed agent
```

```
Use the agentcore power to fetch the last 50 log lines from my agent
```

### Step 3: Create Custom Steering for Your Project

```
Create a steering file that includes:
1. Our specific MCP tool patterns
2. Bedrock best practices for our use case
3. WebSocket communication patterns
4. Deployment checklist
```

This steering file will guide Kiro in future development on this project.

## Module 10: Monitoring and Observability (15 minutes)

### Step 1: View CloudWatch Logs

```bash
# Tail AgentCore logs
aws logs tail /aws/bedrock-agentcore/runtimes/YOUR_AGENT_ID-DEFAULT \
  --log-stream-name-prefix "2026/02/03/[runtime-logs]" \
  --follow
```

### Step 2: Check X-Ray Traces

1. Go to AWS Console → X-Ray
2. View service map
3. Analyze traces for your MCP tools
4. Identify performance bottlenecks

### Step 3: Set Up CloudWatch Dashboard

In Kiro chat:
```
Create a CloudFormation template for a CloudWatch dashboard that monitors:
1. AgentCore invocation count
2. Lambda execution duration
3. WebSocket connection count
4. Bedrock API calls
5. Error rates
```

### Step 4: Deploy Dashboard

```bash
aws cloudformation create-stack \
  --stack-name cfn-builder-dashboard \
  --template-body file://monitoring-dashboard.yaml
```

## Appendix: Architecture Decision Records (ADRs)

Throughout this workshop, we made several key architectural decisions. Understanding the rationale behind these choices will help you make informed decisions in your own projects.

### ADR 1: MCP Server Tools vs. Agents (Deterministic vs. Decision-Making)

**Decision**: Build deterministic MCP server tools instead of autonomous decision-making agents.

**Context**:
We needed to provide CloudFormation capabilities to AI systems. We had two fundamental architectural approaches:
1. **MCP Server Tools**: Deterministic functions that execute specific operations when called
2. **Autonomous Agents**: Decision-making entities that determine what actions to take

**Understanding the Difference**:

**MCP Server Tools (What We Built)**:
```
Nature: Deterministic, passive, function-like
Control: Caller decides WHEN and HOW to use the tool
Logic: "Given these inputs, always produce this output"
Example: build_cfn_template(prompt="Create S3 bucket") → Returns template
Analogy: A calculator - you tell it what to calculate
```

**Autonomous Agents (What We Didn't Build)**:
```
Nature: Decision-making, active, goal-oriented
Control: Agent decides WHAT tools to use and WHEN
Logic: "Given this goal, figure out how to achieve it"
Example: "Deploy infrastructure" → Agent decides to generate template, validate, provision
Analogy: A personal assistant - you give it a goal, it figures out the steps
```

**Decision Rationale**:

**Why MCP Server Tools?**
- ✅ **Predictable**: Same inputs always produce same outputs
- ✅ **Composable**: Caller orchestrates tools into workflows
- ✅ **Debuggable**: Easy to test and troubleshoot individual tools
- ✅ **Flexible**: Different callers can use tools in different ways
- ✅ **Stateless**: No memory or context between calls
- ✅ **Simple**: Each tool has one clear responsibility
- ✅ **Controllable**: Caller maintains full control over execution flow

**Why Not Autonomous Agents?**
- ❌ **Unpredictable**: Agent might choose different approaches for same goal
- ❌ **Complex**: Requires planning, reasoning, and decision-making logic
- ❌ **Harder to Debug**: Agent's decision process can be opaque
- ❌ **Less Flexible**: Agent's workflow is baked into its logic
- ❌ **Stateful**: Requires memory and context management
- ❌ **Overkill**: Our use case doesn't need autonomous decision-making

**Concrete Example**:

**Our MCP Tool Approach**:
```python
# Tool 1: Generate template (deterministic)
@mcp.tool()
def build_cfn_template(prompt: str) -> dict:
    """Always generates a template from the prompt"""
    return generate_template(prompt)

# Tool 2: Validate template (deterministic)
@mcp.tool()
def validate_cfn_template(template: str) -> dict:
    """Always validates the given template"""
    return validate(template)

# Caller orchestrates the workflow:
template = build_cfn_template("Create S3 bucket")
validation = validate_cfn_template(template)
if validation['valid']:
    deploy(template)
```

**Agent Approach (What We Avoided)**:
```python
# Agent decides what to do
class CloudFormationAgent:
    def achieve_goal(self, goal: str):
        # Agent makes decisions:
        # - Should I generate a template?
        # - Should I validate it?
        # - Should I deploy it?
        # - Should I check costs first?
        # - What if validation fails?
        
        # Agent's internal decision-making logic
        if self.needs_template(goal):
            template = self.generate_template()
        if self.should_validate():
            validation = self.validate(template)
        if self.should_deploy():
            self.deploy(template)
```

**Comparison Table**:

| Aspect | MCP Server Tools | Autonomous Agents |
|--------|------------------|-------------------|
| **Decision Making** | Caller decides | Agent decides |
| **Predictability** | Deterministic | Non-deterministic |
| **Control Flow** | External orchestration | Internal planning |
| **State** | Stateless | Stateful (memory) |
| **Complexity** | Simple functions | Complex reasoning |
| **Testing** | Easy (unit tests) | Hard (behavior tests) |
| **Debugging** | Straightforward | Challenging |
| **Flexibility** | High (caller controls) | Lower (agent controls) |
| **Use Case** | Specific operations | Goal achievement |

**Real-World Analogy**:

**MCP Tools = Kitchen Appliances**:
- Microwave: "Heat this for 2 minutes" → Always heats for 2 minutes
- Blender: "Blend these ingredients" → Always blends
- You (the caller) decide: "First blend, then microwave"

**Agents = Personal Chef**:
- You: "Make me dinner"
- Chef decides: What to cook, which tools to use, in what order
- Chef has autonomy and makes decisions

**Our Use Case Analysis**:

We chose MCP tools because:

1. **Clear Operations**: CloudFormation operations are well-defined
   - Generate template → Deterministic
   - Validate template → Deterministic
   - Analyze costs → Deterministic (given same template)

2. **Caller Knows Best**: The UI or orchestrator knows the desired workflow
   - User wants to see architecture first
   - Then generate template
   - Then validate
   - Then analyze costs
   - This sequence shouldn't change based on agent decisions

3. **Composability**: Different callers can use tools differently
   - Web UI: Auto-sequence through all tools
   - CLI: Call individual tools as needed
   - Kiro: Integrate into larger workflows
   - DevOps Agent: Use as part of deployment pipeline

4. **Debugging**: When something fails, we know exactly which tool failed
   - "validate_cfn_template failed" → Clear
   - "Agent failed to achieve goal" → Unclear

**Trade-offs**:

**Pros of Our Approach**:
- ✅ Simple, predictable, testable
- ✅ Caller controls orchestration
- ✅ Easy to add new tools without affecting existing ones
- ✅ Tools can be reused in different contexts

**Cons of Our Approach**:
- ❌ Caller must implement orchestration logic
- ❌ No built-in error recovery or retry logic
- ❌ Can't adapt workflow based on intermediate results
- ❌ Requires caller to understand tool relationships

**When This Becomes an Agent**:

If we later need autonomous behavior, we could build an agent that USES our tools:

```python
class InfrastructureAgent:
    """Agent that uses our MCP tools"""
    
    def deploy_infrastructure(self, requirements: str):
        # Agent decides the workflow
        
        # Step 1: Agent decides to generate template
        template = self.call_tool("build_cfn_template", 
                                  {"prompt": requirements})
        
        # Step 2: Agent decides to validate
        validation = self.call_tool("validate_cfn_template",
                                    {"template": template})
        
        # Step 3: Agent makes decision based on validation
        if not validation['valid']:
            # Agent decides to fix and retry
            template = self.fix_template(template, validation['error'])
            validation = self.call_tool("validate_cfn_template",
                                       {"template": template})
        
        # Step 4: Agent decides whether to deploy
        if validation['valid']:
            self.call_tool("provision_cfn_stack", 
                          {"template": template})
```

**Outcome**:

Building MCP tools instead of agents allowed us to:
- ✅ Keep each tool simple and focused
- ✅ Make the system predictable and debuggable
- ✅ Enable multiple orchestration patterns (UI, CLI, agents)
- ✅ Test each tool independently
- ✅ Let callers control the workflow

**When to Choose MCP Tools**:
- ✅ Operations are well-defined and deterministic
- ✅ Caller knows the desired workflow
- ✅ Need predictability and debuggability
- ✅ Want to support multiple orchestration patterns
- ✅ Building reusable capabilities

**When to Choose Agents**:
- ✅ Need autonomous decision-making
- ✅ Workflow should adapt based on context
- ✅ Want built-in error recovery and planning
- ✅ Goal-oriented rather than operation-oriented
- ✅ Complex multi-step reasoning required

**The Honest Trade-off We Made**:

⚠️ **Important Caveat**: While we call our implementation "MCP tools," we actually violated the pure deterministic tool pattern. Let's be honest about what we built:

**What Pure MCP Tools Should Be**:
```python
@mcp.tool()
def validate_cfn_template(template: str) -> dict:
    """Pure deterministic tool - calls AWS API"""
    cfn = boto3.client('cloudformation')
    return cfn.validate_template(TemplateBody=template)
    # ✅ Same template → Always same result
    # ✅ No LLM involved
    # ✅ Truly deterministic
```

**What We Actually Built**:
```python
@mcp.tool()
def build_cfn_template(prompt: str) -> dict:
    """Actually an agent-like tool - calls LLM"""
    bedrock = boto3.client('bedrock-runtime')
    response = bedrock.invoke_model(
        modelId='claude-sonnet-4-5',
        body={'messages': [{'role': 'user', 'content': prompt}]}
    )
    # ❌ Same prompt → Potentially different results
    # ❌ LLM makes decisions about architecture
    # ❌ Not truly deterministic
```

**Why This Is an Anti-Pattern**:

1. **Non-Deterministic**: Same input can produce different outputs
   - "Create a serverless API" → Might use API Gateway + Lambda one time
   - "Create a serverless API" → Might use AppSync + Lambda another time
   - LLM temperature and model updates affect results

2. **Hidden Decision-Making**: The LLM is making architectural decisions
   - Which AWS services to use
   - How to configure them
   - What best practices to apply
   - This is agent behavior, not tool behavior

3. **Unpredictable**: Hard to test and debug
   - Can't write deterministic unit tests
   - Results vary between runs
   - Difficult to reproduce issues

**Why We Made This Trade-off (Salesforce Integration)**:

We chose this anti-pattern because:

1. **Salesforce Limitation**: Salesforce can't call LLMs directly
   - No native Bedrock integration
   - Can't make complex API calls with auth
   - Limited to simple HTTP requests

2. **User Experience**: Salesforce users need natural language interface
   - Sales teams aren't CloudFormation experts
   - "Create a serverless API" is easier than writing YAML
   - Need AI to translate business requirements to infrastructure

3. **Simplicity**: Wrapping LLM calls in MCP tools was simpler than:
   - Building a separate agent layer
   - Managing agent-to-tool communication
   - Deploying multiple components

**The Better Architecture (What We Should Have Built)**:

```
Salesforce → Agent (with LLM) → Pure MCP Tools → AWS APIs

Agent Layer:
- Makes decisions using LLM
- Determines which tools to call
- Handles orchestration

Pure MCP Tools:
- validate_template() - Calls CloudFormation API
- create_stack() - Calls CloudFormation API  
- get_stack_status() - Calls CloudFormation API
- No LLM calls, purely deterministic
```

**What We Actually Built**:

```
Salesforce → "MCP Tools" (with embedded LLM) → AWS APIs

Hybrid Tools:
- build_cfn_template() - Calls LLM (agent-like)
- validate_template() - Calls API (tool-like)
- analyze_cost() - Calls LLM (agent-like)
```

**Consequences of Our Choice**:

**Pros**:
- ✅ Simpler architecture (one layer instead of two)
- ✅ Works with Salesforce limitations
- ✅ Natural language interface for users
- ✅ Faster to build and deploy

**Cons**:
- ❌ Not truly deterministic tools
- ❌ Harder to test reliably
- ❌ Results vary between runs
- ❌ Violates MCP tool best practices
- ❌ Mixing concerns (decision-making + execution)

**When This Pattern Is Acceptable**:

Use LLM-powered "tools" when:
- ✅ Caller can't access LLMs directly (like Salesforce)
- ✅ Natural language interface is required
- ✅ Non-determinism is acceptable
- ✅ Simplicity outweighs purity
- ✅ You understand and accept the trade-offs

**When to Use Pure Tools**:

Use deterministic tools when:
- ✅ Predictability is critical
- ✅ Testing must be reliable
- ✅ Caller can handle LLM calls
- ✅ Following best practices matters
- ✅ Building reusable infrastructure

**Our Recommendation**:

If building this again, we would:
1. **Separate concerns**: Build an agent layer + pure tools
2. **Agent layer**: Handles LLM calls and decision-making
3. **Tool layer**: Pure deterministic operations
4. **Trade-off**: More complex but follows best practices

However, for a Salesforce integration demo, our hybrid approach was pragmatic and acceptable given the constraints.

**Key Takeaway**: We built "agent-like tools" rather than "pure tools" as a pragmatic trade-off for Salesforce integration. This violates MCP best practices but solved our real-world constraint. Be aware of this trade-off when designing your own systems.

---

### ADR 2: AgentCore Runtime vs. Bedrock Agents

**Decision**: Deploy MCP server to Amazon Bedrock AgentCore Runtime instead of using Bedrock Agents.

**Context**:
We needed a production hosting platform for our MCP server. AWS offers two main options:
1. Amazon Bedrock Agents (managed agent service)
2. Amazon Bedrock AgentCore Runtime (MCP server hosting platform)

**Decision Rationale**:

**Why AgentCore Runtime?**
- ✅ **Native MCP Support**: Built specifically for hosting MCP servers
- ✅ **Container Deployment**: Supports custom dependencies (GraphViz for diagrams)
- ✅ **Stateless HTTP**: Optimized for MCP's streamable HTTP transport
- ✅ **Extended Timeouts**: Up to 10 minutes for long-running operations
- ✅ **Direct Control**: Full control over tool implementation and logic
- ✅ **Session Management**: Automatic handling of MCP sessions
- ✅ **Cost-Effective**: Pay only for actual invocations, scales to zero

**Why Not Bedrock Agents?**
- ❌ **Limited Tool Control**: Tools defined through AWS console/API, less flexibility
- ❌ **No Container Support**: Can't easily add system dependencies like GraphViz
- ❌ **Action Groups**: Requires Lambda functions for each action group
- ❌ **Less Direct**: Additional abstraction layer between your code and the model
- ❌ **Orchestration Focus**: Designed for multi-step agent workflows, not simple tool servers

**Comparison Table**:

| Feature | AgentCore Runtime | Bedrock Agents |
|---------|------------------|----------------|
| **MCP Support** | Native | Via Lambda adapters |
| **Container Deployment** | ✅ Yes | ❌ No |
| **Custom Dependencies** | ✅ Yes (GraphViz, etc.) | ❌ Limited |
| **Tool Definition** | Code-based (Python) | Console/API-based |
| **Timeout** | 10 minutes | 30 seconds (Lambda) |
| **Orchestration** | Manual | Built-in |
| **Memory** | External (DynamoDB) | Built-in |
| **Cost Model** | Per invocation | Per invocation + storage |
| **Best For** | Tool servers | Multi-step agents |

**Trade-offs**:
- **Pro**: AgentCore gives us full control and container support
- **Con**: We handle orchestration ourselves (not needed for our use case)
- **Pro**: Native MCP support means less adapter code
- **Con**: Bedrock Agents has built-in memory and orchestration (we don't need it)

**Outcome**:
AgentCore Runtime enabled us to:
- Deploy GraphViz for professional diagram generation
- Implement 7 tools with full control over logic
- Handle long-running operations (30-45 seconds for full sequence)
- Use standard MCP protocol without adapters
- Scale automatically with zero idle cost

**When to Choose AgentCore Runtime**:
- ✅ Building MCP servers with custom dependencies
- ✅ Need container deployment
- ✅ Want direct control over tool implementation
- ✅ Simple tool server without complex orchestration
- ✅ Long-running operations (>30 seconds)

**When to Choose Bedrock Agents**:
- ✅ Need built-in orchestration and planning
- ✅ Want managed memory and conversation history
- ✅ Building multi-step agent workflows
- ✅ Prefer console-based tool configuration
- ✅ Don't need custom system dependencies

---

### ADR 3: Agent-to-Agent (A2A) vs. MCP

**Decision**: Use MCP for tool integration instead of Agent-to-Agent (A2A) communication.

**Context**:
We needed to integrate our CloudFormation tools with AI models and potentially other agents. We considered:
1. Model Context Protocol (MCP) for tool exposure
2. Agent-to-Agent (A2A) protocol for agent communication

**Decision Rationale**:

**Why MCP?**
- ✅ **Tool-Focused**: Designed specifically for exposing tools to AI models
- ✅ **Simpler Model**: Request-response pattern, easier to implement
- ✅ **Stateless**: Each tool call is independent, easier to scale
- ✅ **Mature Ecosystem**: FastMCP, AgentCore Runtime, Claude Desktop support
- ✅ **Type Safety**: Strong typing for parameters and return values
- ✅ **Our Use Case**: We're building a tool server, not an autonomous agent

**Why Not A2A?**
- ❌ **Agent-Focused**: Designed for agent-to-agent communication, not tool exposure
- ❌ **More Complex**: Requires agent identity, capabilities negotiation, conversation management
- ❌ **Overkill**: We don't need agent autonomy or peer-to-peer communication
- ❌ **Less Mature**: Newer protocol with fewer implementations
- ❌ **Different Purpose**: A2A is for agents collaborating, not tools serving models

**Understanding the Difference**:

**MCP (Model Context Protocol)**:
```
Purpose: Connect AI models to tools and data sources
Pattern: Client-Server (Model → MCP Server)
Use Case: "I need to call a CloudFormation API"
Example: Claude Desktop → MCP Server → AWS API
```

**A2A (Agent-to-Agent)**:
```
Purpose: Enable agents to communicate and collaborate
Pattern: Peer-to-Peer (Agent ↔ Agent)
Use Case: "I need another agent's help to complete my task"
Example: DevOps Agent → Architecture Agent → Cost Agent
```

**Comparison Table**:

| Aspect | MCP | A2A |
|--------|-----|-----|
| **Purpose** | Tool integration | Agent collaboration |
| **Pattern** | Client-Server | Peer-to-Peer |
| **Complexity** | Simple | Complex |
| **State** | Stateless | Stateful |
| **Identity** | Not required | Agent identity required |
| **Autonomy** | Tools are passive | Agents are autonomous |
| **Use Case** | Expose functions | Coordinate workflows |
| **Maturity** | Established | Emerging |

**When to Use Each**:

**Use MCP When**:
- ✅ Exposing tools/functions to AI models
- ✅ Building stateless tool servers
- ✅ Need simple request-response pattern
- ✅ Integrating with existing APIs
- ✅ Want type-safe tool definitions

**Use A2A When**:
- ✅ Building autonomous agents that collaborate
- ✅ Need agent-to-agent negotiation
- ✅ Coordinating complex multi-agent workflows
- ✅ Agents need to discover and communicate with peers
- ✅ Building agent ecosystems

**Our Decision**:
We chose MCP because:
1. **We're building tools, not agents**: Our CloudFormation operations are functions, not autonomous agents
2. **Simpler is better**: MCP's request-response model fits our needs perfectly
3. **Ecosystem support**: AgentCore Runtime, FastMCP, and Claude Desktop all support MCP
4. **Stateless design**: Each tool call is independent, making scaling easier
5. **Type safety**: MCP's strong typing prevents errors

**Future Consideration**:
If we later need to build a DevOps Agent that coordinates with our CloudFormation tools, we could:
- Keep MCP for tool exposure (CloudFormation operations)
- Add A2A for agent coordination (DevOps Agent ↔ Architecture Agent)
- Use both protocols for different purposes

**Trade-offs**:
- **Pro**: MCP is simpler and perfectly suited for our tool server use case
- **Con**: If we need agent-to-agent collaboration later, we'd need to add A2A
- **Pro**: MCP has better tooling and ecosystem support today
- **Con**: A2A might be better for future multi-agent scenarios (but we can add it later)

**Outcome**:
Using MCP allowed us to:
- Build a simple, scalable tool server
- Leverage AgentCore Runtime's native MCP support
- Integrate easily with multiple clients (Kiro, web UI, Claude Desktop)
- Keep the architecture simple and maintainable

---

### Summary of ADRs

| Decision | Choice | Key Reason |
|----------|--------|------------|
| **Tool Protocol** | MCP over Custom | Open standard, type safety, ecosystem |
| **Hosting Platform** | AgentCore over Bedrock Agents | Container support, MCP native, control |
| **Communication Pattern** | MCP over A2A | Tool server, not agent collaboration |

These decisions shaped our architecture and enabled us to build a production-ready solution efficiently. Understanding these trade-offs will help you make informed choices in your own projects.

---

## Module 11: Cleanup (10 minutes)

**IMPORTANT**: Clean up resources to avoid ongoing charges!

### Step 1: Delete AgentCore Runtime

```bash
agentcore destroy
```

This removes:
- AgentCore Runtime
- ECR repository
- IAM roles
- CloudWatch log groups

### Step 2: Delete WebSocket Stack

```bash
aws cloudformation delete-stack \
  --stack-name cfn-builder-websocket

# Wait for deletion
aws cloudformation wait stack-delete-complete \
  --stack-name cfn-builder-websocket
```

### Step 3: Delete Amplify App (if deployed)

1. Go to AWS Amplify Console
2. Select your app
3. Click "Actions" → "Delete app"

### Step 4: Delete CloudWatch Dashboard (if created)

```bash
aws cloudformation delete-stack \
  --stack-name cfn-builder-dashboard
```

### Step 5: Verify Cleanup

```bash
# Check for remaining resources
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `cfn-builder`)].StackName'
```

## Workshop Recap

### What You Built

✅ MCP server with 7 AI-powered tools  
✅ Integration with Claude Sonnet 4.5 via Bedrock  
✅ Professional diagram generation with GraphViz  
✅ WebSocket backend for real-time communication  
✅ Modern web UI with auto-sequencing  
✅ Production deployment on AgentCore Runtime  
✅ Complete observability with CloudWatch and X-Ray  

### What You Learned

✅ Using Kiro AI IDE for accelerated development  
✅ Building MCP servers with FastMCP  
✅ Deploying to Amazon Bedrock AgentCore Runtime  
✅ Integrating generative AI with AWS services  
✅ Creating real-time AI applications with WebSocket  
✅ Using Kiro's steering files and powers  
✅ Implementing specs for structured development  

### Key Takeaways

1. **Kiro accelerates AI agent development** through context-aware assistance, steering files, and powers
2. **MCP provides a standard protocol** for AI tool integration
3. **AgentCore Runtime simplifies deployment** of MCP servers with auto-scaling and observability
4. **WebSocket enables real-time AI interactions** without timeout limitations
5. **Steering files capture project knowledge** for consistent AI assistance

## Next Steps

### Extend Your Solution

1. **Add more tools**:
   - Terraform generation
   - Kubernetes manifest creation
   - Security scanning
   - Compliance checking

2. **Improve the UI**:
   - Template versioning
   - Collaboration features
   - Template library
   - Export options

3. **Enhance observability**:
   - Custom metrics
   - Alerting
   - Performance optimization
   - Cost tracking

### Learn More

- [Kiro Documentation](https://kiro.dev/docs)
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)

### Share Your Work

- Blog about your experience
- Share on social media with #KiroAI #AWSAgentCore
- Contribute to open source MCP servers
- Join the Kiro community

## Troubleshooting

### Common Issues

**Issue**: "Module 'mcp' not found"  
**Solution**: Activate virtual environment and reinstall dependencies
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Issue**: "Bedrock throttling errors"  
**Solution**: Implement retry logic with exponential backoff (already included in workshop code)

**Issue**: "GraphViz not found"  
**Solution**: Install GraphViz system package
```bash
brew install graphviz  # macOS
sudo apt-get install graphviz  # Linux
```

**Issue**: "WebSocket connection failed"  
**Solution**: Check WebSocket URL and ensure Lambda has correct permissions

**Issue**: "AgentCore deployment failed"  
**Solution**: Check CloudWatch logs for detailed error messages
```bash
aws logs tail /aws/codebuild/agentcore-build --follow
```

## Feedback

We'd love to hear about your workshop experience!

- What worked well?
- What was challenging?
- What would you like to see added?

Share feedback: [workshop-feedback@example.com]

---

**Congratulations!** You've completed the workshop and built a production-ready AI-powered infrastructure tool using Kiro, Amazon Bedrock AgentCore, and MCP. 🎉
