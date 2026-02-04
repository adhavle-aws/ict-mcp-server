# AWS DevOps Agent Integration Research

## Overview

AWS DevOps Agent is a frontier agent that can monitor and manage CloudFormation stacks. It can be configured to use MCP servers for extended capabilities.

## Key Findings

### 1. What is AWS DevOps Agent?

- **Purpose**: Autonomous incident resolution and prevention
- **Capabilities**: 
  - Monitors CloudFormation stacks
  - Analyzes CloudWatch logs and metrics
  - Correlates deployment data with incidents
  - Provides mitigation recommendations
  - Learns from historical incidents
- **Region**: Currently only runs in us-east-1 (but can monitor resources globally)

### 2. How MCP Servers Connect to DevOps Agent

DevOps Agent can consume MCP servers to extend its investigation capabilities:

```
DevOps Agent → MCP Server → Your Tools/Data
```

**Registration Process**:
1. MCP servers are registered at **AWS account level**
2. Shared among all "Agent Spaces" in that account
3. Each Agent Space selects which tools to use

### 3. CloudFormation Resource for MCP Integration

AWS provides a CloudFormation resource type:

```yaml
AWS::DevOpsAgent::Association
  Properties:
    MCPServerConfiguration:
      Name: String (required)
      Endpoint: String (required, HTTPS URL)
      Tools: [String] (required, list of tool names)
      Description: String (optional)
      EnableWebhookUpdates: Boolean (optional)
```

**Example**:
```yaml
DevOpsAgentMCPAssociation:
  Type: AWS::DevOpsAgent::Association
  Properties:
    AgentSpaceId: !Ref MyAgentSpace
    MCPServerConfiguration:
      Name: CFNArchitectMCP
      Endpoint: https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A611291728384%3Aruntime%2Fcfn_mcp_server-4KOBaDFd4a/invocations
      Tools:
        - generate_architecture_overview
        - build_cfn_template
        - validate_cfn_template
        - well_architected_review
        - analyze_cost_optimization
      Description: CloudFormation architecture design and analysis tools
```

### 4. Authentication Methods

DevOps Agent supports 3 authentication methods for MCP servers:

1. **OAuth Client Credentials** (recommended for production)
2. **OAuth 3LO** (Three-Legged OAuth)
3. **API Key**

For AgentCore MCP servers, use **IAM authentication** (SigV4).

### 5. Agent Space Concept

DevOps Agent uses "Agent Spaces" to organize monitoring:

- **Agent Space** = A monitoring scope for your application
- Can be initialized from:
  - CloudFormation stacks
  - AWS Tags
  - Manual resource selection
- Each space can have multiple MCP servers attached

## Integration Architecture

### Current Setup (CFN MCP Server)

```
User → UI → WebSocket → Lambda → AgentCore MCP Server → AWS Services
```

### With DevOps Agent Integration

```
User → Onboarding Agent → Creates CFN Stack
                        ↓
                   Configures DevOps Agent
                        ↓
DevOps Agent → Monitors Stack → Uses CFN MCP Server for analysis
```

## How Onboarding Agent Can Configure DevOps Agent

### Option 1: CloudFormation Template Approach

The onboarding agent can **include DevOps Agent configuration in the CloudFormation template** it generates:

```yaml
# In the generated CloudFormation template

Resources:
  # ... your infrastructure resources ...
  
  # DevOps Agent Space for this stack
  MyAppAgentSpace:
    Type: AWS::DevOpsAgent::AgentSpace
    Properties:
      Name: !Sub "${AWS::StackName}-monitoring"
      Description: DevOps Agent monitoring for this stack
      InitialTopology:
        CloudFormationStacks:
          - !Ref AWS::StackId
  
  # Associate CFN MCP Server with Agent Space
  MCPServerAssociation:
    Type: AWS::DevOpsAgent::Association
    Properties:
      AgentSpaceId: !Ref MyAppAgentSpace
      MCPServerConfiguration:
        Name: CFNArchitectMCP
        Endpoint: https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/[AGENT_ARN]/invocations
        Tools:
          - generate_architecture_overview
          - build_cfn_template
          - validate_cfn_template
          - well_architected_review
          - analyze_cost_optimization
        Description: Architecture analysis and optimization tools
  
  # IAM Role for DevOps Agent
  DevOpsAgentRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: devopsagent.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/ReadOnlyAccess
      Policies:
        - PolicyName: AgentCoreAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - bedrock-agentcore:InvokeRuntime
                Resource: !Sub "arn:aws:bedrock-agentcore:us-east-1:${AWS::AccountId}:runtime/*"
```

### Option 2: Post-Deployment Configuration

The onboarding agent can use AWS SDK to configure DevOps Agent after stack creation:

```python
import boto3

def configure_devops_agent_for_stack(stack_name, stack_id, mcp_server_arn):
    """
    Configure DevOps Agent to monitor a CloudFormation stack
    using the CFN MCP Server for analysis
    """
    devops_client = boto3.client('devopsagent', region_name='us-east-1')
    
    # 1. Create Agent Space for the stack
    agent_space = devops_client.create_agent_space(
        name=f"{stack_name}-monitoring",
        description=f"DevOps Agent monitoring for {stack_name}",
        initialTopology={
            'cloudFormationStacks': [stack_id]
        }
    )
    
    agent_space_id = agent_space['agentSpaceId']
    
    # 2. Register MCP Server (if not already registered)
    try:
        devops_client.register_mcp_server(
            name='CFNArchitectMCP',
            endpoint=f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{mcp_server_arn}/invocations",
            authenticationMethod='IAM',
            description='CloudFormation architecture design and analysis'
        )
    except devops_client.exceptions.ResourceAlreadyExistsException:
        pass  # Already registered
    
    # 3. Associate MCP Server with Agent Space
    devops_client.create_association(
        agentSpaceId=agent_space_id,
        mcpServerConfiguration={
            'name': 'CFNArchitectMCP',
            'endpoint': f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{mcp_server_arn}/invocations",
            'tools': [
                'generate_architecture_overview',
                'build_cfn_template',
                'validate_cfn_template',
                'well_architected_review',
                'analyze_cost_optimization'
            ]
        }
    )
    
    return {
        'agent_space_id': agent_space_id,
        'agent_space_url': f"https://console.aws.amazon.com/devopsagent/home?region=us-east-1#/spaces/{agent_space_id}"
    }
```

### Option 3: Hybrid Approach (Recommended)

1. **Onboarding Agent** generates CloudFormation template with DevOps Agent resources
2. **User deploys** the stack (includes DevOps Agent setup)
3. **DevOps Agent** automatically starts monitoring
4. **DevOps Agent** uses CFN MCP Server tools for analysis

## Benefits of Integration

### For the User:

1. **Automatic Monitoring**: Every stack gets DevOps Agent monitoring
2. **Proactive Alerts**: DevOps Agent detects issues before they impact users
3. **AI-Powered Analysis**: Uses CFN MCP Server tools for root cause analysis
4. **Continuous Improvement**: DevOps Agent learns from incidents

### For DevOps Agent:

1. **Architecture Context**: Can query the original design decisions
2. **Template Analysis**: Can review the CloudFormation template
3. **Cost Insights**: Can analyze cost optimization opportunities
4. **Best Practices**: Can check Well-Architected compliance

## Implementation Plan

### Phase 1: Enhance Onboarding Agent

Add a new tool to the onboarding agent:

```python
@tool
def configure_devops_monitoring(stack_name: str, stack_id: str) -> dict:
    """
    Configure AWS DevOps Agent to monitor the deployed stack
    using the CFN MCP Server for analysis capabilities
    """
    # Implementation using boto3 devopsagent client
    pass
```

### Phase 2: Update CloudFormation Templates

Modify the `build_cfn_template` tool to optionally include DevOps Agent resources:

```python
def build_cfn_template(prompt: str, include_devops_agent: bool = True):
    # Generate base template
    template = generate_infrastructure(prompt)
    
    if include_devops_agent:
        # Add DevOps Agent resources
        template['Resources']['DevOpsAgentSpace'] = {...}
        template['Resources']['MCPServerAssociation'] = {...}
        template['Resources']['DevOpsAgentRole'] = {...}
    
    return template
```

### Phase 3: Workflow Integration

```
User: "Create a serverless API"
  ↓
Onboarding Agent:
  1. Generates architecture
  2. Creates CloudFormation template (with DevOps Agent resources)
  3. Validates template
  4. Deploys stack
  5. Configures DevOps Agent to monitor the stack
  6. Returns: Stack ID + DevOps Agent Space URL
  ↓
DevOps Agent:
  - Monitors the deployed stack
  - Uses CFN MCP Server tools for analysis
  - Alerts on issues
  - Provides optimization recommendations
```

## Required Changes

### 1. Add DevOps Agent SDK

```python
# requirements.txt
boto3>=1.34.0  # Includes devopsagent client
```

### 2. Add Tool to Onboarding Agent

```python
@tool
def setup_devops_monitoring(
    stack_name: str,
    stack_id: str,
    mcp_server_arn: str = "arn:aws:bedrock-agentcore:us-east-1:611291728384:runtime/cfn_mcp_server-4KOBaDFd4a"
) -> dict:
    """
    Configure AWS DevOps Agent to monitor a CloudFormation stack.
    Creates an Agent Space and associates the CFN MCP Server.
    """
    # Implementation here
    pass
```

### 3. Update System Prompt

Add to onboarding agent's system prompt:

```
After deploying a stack, automatically configure AWS DevOps Agent 
to monitor it using the setup_devops_monitoring tool. This enables:
- Continuous monitoring
- Incident detection
- AI-powered analysis using CFN MCP Server tools
```

## Example Flow

```
User: "Create a 3-tier web app"

Onboarding Agent:
1. ✅ Generates architecture overview
2. ✅ Creates CloudFormation template
3. ✅ Validates template
4. ✅ Deploys stack → Stack ID: stack-xyz
5. ✅ Configures DevOps Agent:
   - Creates Agent Space: "3-tier-web-app-monitoring"
   - Associates CFN MCP Server
   - Enables monitoring
6. ✅ Returns:
   - Stack URL
   - DevOps Agent Space URL
   - Monitoring dashboard link

User: [Later, if incident occurs]

DevOps Agent:
1. 🚨 Detects issue in stack
2. 🔍 Investigates using CFN MCP Server tools:
   - Calls well_architected_review on the stack
   - Calls analyze_cost_optimization
   - Analyzes CloudWatch logs
3. 💡 Provides recommendations
4. 🔧 Can auto-remediate (if configured)
```

## Security Considerations

1. **IAM Permissions**: DevOps Agent needs permission to invoke AgentCore MCP Server
2. **Least Privilege**: Only grant necessary tools to each Agent Space
3. **Audit Trail**: All DevOps Agent actions are logged in CloudWatch
4. **Data Privacy**: MCP server runs in your account, data doesn't leave AWS

## Cost Implications

- **DevOps Agent**: Pay per Agent Space (~$X/month)
- **MCP Server Calls**: Bedrock API calls when DevOps Agent uses tools
- **CloudWatch**: Additional logs and metrics storage

## Limitations

- DevOps Agent currently only runs in **us-east-1**
- Can monitor resources in any region
- MCP server must be HTTPS endpoint
- Maximum 64 characters for tool names

## Recommendations

### For Your Use Case:

1. **Start Simple**: Add DevOps Agent configuration as optional in templates
2. **User Choice**: Let users opt-in to DevOps Agent monitoring
3. **Gradual Rollout**: Test with a few stacks first
4. **Monitor Costs**: Track Bedrock API usage from DevOps Agent

### Implementation Priority:

1. ✅ **High**: Add CloudFormation resources for DevOps Agent (easy, declarative)
2. ✅ **Medium**: Add post-deployment configuration tool (more flexible)
3. ⏳ **Low**: Auto-configure for all stacks (wait for user feedback)

## Next Steps (No Code Changes Yet)

1. **Test DevOps Agent**: Create a test Agent Space manually in console
2. **Register CFN MCP Server**: Connect it to DevOps Agent
3. **Monitor a Stack**: See how DevOps Agent uses the MCP tools
4. **Evaluate Value**: Determine if automatic configuration is worth it

## Conclusion

**Yes, it's possible!** The onboarding agent can automatically configure DevOps Agent for stacks it creates by:

1. **Including DevOps Agent resources in CloudFormation templates** (easiest)
2. **Using AWS SDK to configure post-deployment** (more flexible)
3. **Hybrid approach** (recommended)

The CFN MCP Server tools would be valuable for DevOps Agent because they provide:
- Architecture context and design decisions
- Well-Architected analysis
- Cost optimization insights
- Template validation

This would make DevOps Agent more intelligent about the stacks it monitors!

---

**Research Complete** - No code changes made, just analysis and recommendations.
