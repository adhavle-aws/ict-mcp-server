# CloudFormation MCP Server - Demo Summary

## What It Does

AI-powered infrastructure design platform that transforms natural language into production-ready CloudFormation templates with comprehensive analysis.

## Live Demo

**URL**: https://main.d8fhq0k6egfqk.amplifyapp.com

**Try It**: Click any example button (3-Tier, Serverless, Data Pipeline, Microservices) and hit Generate.

## Architecture

```
Browser (Amplify)
    ↓ WebSocket
API Gateway WebSocket
    ↓ Async Invocation
Lambda (SigV4 Signing)
    ↓ HTTPS + IAM Auth
AgentCore Runtime (Container)
    ↓
MCP Server (7 Tools)
    ↓
Claude Sonnet 3.5 (Bedrock)
```

## Workflow

```
User: "Create a 3-tier web application"
    ↓
1. Architecture Overview
   - ASCII diagram with AWS icons
   - Component breakdown with reasoning
   - Design decisions explained
    ↓
2. Well-Architected Review
   - 6-pillar analysis
   - References specific components
   - Actionable recommendations
    ↓
3. Cost Optimization
   - Builds on WAR findings
   - Concrete cost estimates
   - Implementation roadmap
    ↓
4. CloudFormation Template
   - Production-ready YAML
   - Validate via AWS API
   - Deploy to AWS
```

## Key Features

- **Chained Analysis**: Each step builds on previous context
- **Specific Recommendations**: References actual components, not generic advice
- **Cost Estimates**: Dollar amounts and savings calculations
- **ASCII Diagrams**: Visual architecture with AWS icons
- **No Timeouts**: WebSocket + async Lambda handles long operations
- **Secure**: IAM authentication, no public endpoints

## Technology Stack

- **Frontend**: Amplify (auto-deploy from Git)
- **Backend**: API Gateway WebSocket + Lambda
- **MCP Server**: AgentCore Runtime (serverless container)
- **AI**: Claude Sonnet 3.5 via Bedrock
- **Auth**: AWS IAM (SigV4)

## MCP Tools (7)

1. `generate_architecture_overview` - Text summary with ASCII diagram
2. `well_architected_review` - 6-pillar analysis
3. `analyze_cost_optimization` - Cost analysis with estimates
4. `build_cfn_template` - Generate CloudFormation
5. `validate_cfn_template` - Validate via AWS API
6. `provision_cfn_stack` - Deploy to AWS
7. `generate_architecture_diagram` - Professional PNG (in development)

## Repository

**GitHub**: https://github.com/adhavle-aws/ict-mcp-server

## Deployment

- **MCP Server**: `arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-VpWbdyCLTH`
- **WebSocket**: `wss://z832i481e5.execute-api.us-east-1.amazonaws.com/prod`
- **Frontend**: https://main.d8fhq0k6egfqk.amplifyapp.com

## Cost

~$20-40/month for 10,000 requests (mostly Bedrock/Claude usage)

---

**Status**: ✅ Production-ready with contextual, chained analysis workflow
