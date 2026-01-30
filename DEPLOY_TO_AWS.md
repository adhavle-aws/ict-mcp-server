# Deploy CloudFormation Builder UI to AWS

## Architecture

```
GitHub → AWS Amplify (Frontend) → API Gateway → Lambda → AgentCore Runtime
         (Static hosting)          (Backend)    (SigV4)   (MCP Server)
```

## Step 1: Deploy Backend Infrastructure

```bash
# Deploy API Gateway + Lambda
aws cloudformation create-stack \
  --stack-name cfn-builder-backend \
  --template-body file://deploy/infrastructure.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=AgentArn,ParameterValue=arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-CxkrO53RPH

# Wait for completion
aws cloudformation wait stack-create-complete --stack-name cfn-builder-backend

# Get API endpoint
aws cloudformation describe-stacks \
  --stack-name cfn-builder-backend \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text
```

## Step 2: Update Frontend with API Endpoint

Update `ui/frontend/index.html`:

```javascript
const BACKEND_URL = 'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod';
```

## Step 3: Initialize Git Repository

```bash
# Initialize git (if not already)
git init
git add .
git commit -m "Initial commit - CloudFormation Builder"

# Create GitHub repo and push
gh repo create cfn-builder --public --source=. --remote=origin --push
# Or manually create repo on GitHub and:
git remote add origin https://github.com/YOUR_USERNAME/cfn-builder.git
git push -u origin main
```

## Step 4: Deploy with AWS Amplify

### Option A: AWS Console (Easiest)

1. Go to [AWS Amplify Console](https://console.aws.amazon.com/amplify/)
2. Click "New app" → "Host web app"
3. Select "GitHub"
4. Authorize AWS Amplify to access your GitHub
5. Select your repository: `cfn-builder`
6. Select branch: `main`
7. Build settings:
   - Build command: (leave default)
   - Base directory: `ui/frontend`
   - Output directory: `/`
8. Click "Save and deploy"

### Option B: AWS CLI

```bash
# Create Amplify app
aws amplify create-app \
  --name cfn-builder \
  --repository https://github.com/YOUR_USERNAME/cfn-builder \
  --oauth-token YOUR_GITHUB_TOKEN \
  --build-spec file://amplify.yml

# Create branch
aws amplify create-branch \
  --app-id YOUR_APP_ID \
  --branch-name main

# Start deployment
aws amplify start-job \
  --app-id YOUR_APP_ID \
  --branch-name main \
  --job-type RELEASE
```

### Option C: AWS CDK (Infrastructure as Code)

```typescript
// amplify-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as amplify from 'aws-cdk-lib/aws-amplify';

export class AmplifyStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const amplifyApp = new amplify.CfnApp(this, 'CfnBuilderApp', {
      name: 'cfn-builder',
      repository: 'https://github.com/YOUR_USERNAME/cfn-builder',
      oauthToken: process.env.GITHUB_TOKEN,
      buildSpec: `
version: 1
frontend:
  phases:
    build:
      commands:
        - cp ui/frontend/index.html index.html
  artifacts:
    baseDirectory: /
    files:
      - index.html
      `,
    });

    new amplify.CfnBranch(this, 'MainBranch', {
      appId: amplifyApp.attrAppId,
      branchName: 'main',
      enableAutoBuild: true,
    });
  }
}
```

## Step 5: Configure Environment Variables in Amplify

In Amplify Console:
1. Go to your app
2. Click "Environment variables"
3. Add:
   - `BACKEND_URL` = Your API Gateway URL

Or via CLI:
```bash
aws amplify update-app \
  --app-id YOUR_APP_ID \
  --environment-variables BACKEND_URL=https://YOUR_API.execute-api.us-east-1.amazonaws.com/prod
```

## Step 6: Update Frontend to Use Environment Variable

```javascript
// In index.html
const BACKEND_URL = window.AMPLIFY_ENV?.BACKEND_URL || 'http://localhost:3001';
```

## Complete Deployment Script

```bash
#!/bin/bash
# deploy-to-aws.sh

set -e

echo "🚀 Deploying CloudFormation Builder to AWS"
echo ""

# Step 1: Deploy backend
echo "Step 1: Deploying backend infrastructure..."
aws cloudformation create-stack \
  --stack-name cfn-builder-backend \
  --template-body file://deploy/infrastructure.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=AgentArn,ParameterValue=arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-CxkrO53RPH

echo "Waiting for backend deployment..."
aws cloudformation wait stack-create-complete --stack-name cfn-builder-backend

# Get API endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name cfn-builder-backend \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

echo "✅ Backend deployed: $API_ENDPOINT"
echo ""

# Step 2: Update frontend
echo "Step 2: Updating frontend with API endpoint..."
sed -i.bak "s|http://localhost:3001|$API_ENDPOINT|g" ui/frontend/index.html

# Step 3: Commit and push
echo "Step 3: Committing changes..."
git add .
git commit -m "Update API endpoint for production"
git push

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Go to AWS Amplify Console"
echo "2. Connect your GitHub repository"
echo "3. Deploy the app"
echo ""
echo "Your API endpoint: $API_ENDPOINT"
```

## Architecture Benefits

✅ **Frontend (Amplify)**:
- Global CDN distribution
- HTTPS by default
- Automatic builds on git push
- Custom domain support
- Free tier: 1000 build minutes/month

✅ **Backend (Lambda + API Gateway)**:
- Serverless, auto-scaling
- Pay per request
- Built-in CORS
- CloudWatch logging
- No server management

✅ **MCP Server (AgentCore)**:
- Already deployed
- IAM authentication
- Observability built-in

## Cost Estimate

For 10,000 requests/month:
- **Amplify**: $0 (free tier)
- **API Gateway**: $0.035
- **Lambda**: $0.20
- **AgentCore**: Included

**Total**: ~$0.25/month

## Monitoring

```bash
# Backend logs
aws logs tail /aws/lambda/cfn-builder-backend --follow

# API Gateway logs
aws logs tail /aws/apigateway/cfn-builder-api --follow

# MCP Server logs
aws logs tail /aws/bedrock-agentcore/runtimes/mcp_server-CxkrO53RPH-DEFAULT --follow
```

## Cleanup

```bash
# Delete Amplify app
aws amplify delete-app --app-id YOUR_APP_ID

# Delete backend
aws cloudformation delete-stack --stack-name cfn-builder-backend

# Delete MCP server
agentcore destroy
```

## Next Steps

1. ✅ Deploy backend infrastructure
2. ✅ Push code to GitHub
3. ✅ Connect Amplify to GitHub
4. ✅ Deploy frontend
5. ✅ Test end-to-end

Your CloudFormation Builder will be live on AWS! 🚀
