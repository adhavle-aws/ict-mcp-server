# ✅ Deployed to AWS!

## Backend Infrastructure

**Status**: ✅ DEPLOYED

- **API Gateway**: `https://tuzwz6hzq7.execute-api.us-east-1.amazonaws.com/prod`
- **Lambda**: `cfn-builder-backend` (NOT publicly accessible)
- **Stack**: `cfn-builder-backend`

### Security ✅
- Lambda has NO function URL
- Only API Gateway can invoke Lambda
- Resource-based policy restricts access
- CORS enabled for frontend

## MCP Server

**Status**: ✅ DEPLOYED

- **ARN**: `arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-CxkrO53RPH`
- **Tools**: 6 tools (build, validate, provision, architecture, cost, well-architected)
- **Authentication**: IAM (SigV4)

## Frontend

**Status**: ✅ READY FOR AMPLIFY

- **File**: `ui/frontend/index.html`
- **Backend URL**: Updated to production API Gateway
- **Ready to deploy**: Push to GitHub → Connect Amplify

## Next Steps for Amplify

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "CloudFormation Builder - Production Ready"
gh repo create cfn-builder --public --source=. --push
```

### 2. Deploy with Amplify Console

1. Go to: https://console.aws.amazon.com/amplify/
2. Click "New app" → "Host web app"
3. Select "GitHub"
4. Choose your repository
5. Build settings:
   - Build command: (leave default)
   - Base directory: `ui/frontend`
   - Output directory: `/`
6. Click "Save and deploy"

### 3. Your App Will Be Live!

URL: `https://main.YOUR_APP_ID.amplifyapp.com`

## Test Backend Now

```bash
curl -X POST https://tuzwz6hzq7.execute-api.us-east-1.amazonaws.com/prod/api/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "build_cfn_template",
      "arguments": {
        "prompt": "Create an S3 bucket",
        "format": "yaml"
      }
    }
  }'
```

## Architecture

```
GitHub → AWS Amplify (Frontend)
         ↓
         API Gateway (Backend)
         ↓
         Lambda (SigV4 signing) - NOT PUBLIC
         ↓
         AgentCore Runtime (MCP Server)
         ↓
         Claude + CloudFormation
```

## Monitoring

```bash
# Lambda logs
aws logs tail /aws/lambda/cfn-builder-backend --follow

# MCP Server logs
aws logs tail /aws/bedrock-agentcore/runtimes/mcp_server-CxkrO53RPH-DEFAULT --follow
```

## Cleanup

```bash
# Delete backend
aws cloudformation delete-stack --stack-name cfn-builder-backend

# Delete MCP server
agentcore destroy

# Delete Amplify app (after deploying)
aws amplify delete-app --app-id YOUR_APP_ID
```

Your CloudFormation Builder is production-ready! 🚀
