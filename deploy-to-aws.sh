#!/bin/bash
# Deploy CloudFormation Builder to AWS (Lambda + API Gateway).
# Uses AWS profile aws-gaurav. Frontend deploys via Amplify on git push.

set -e

export AWS_PROFILE="${AWS_PROFILE:-aws-gaurav}"

echo "🚀 Deploying CloudFormation Builder to AWS (profile: $AWS_PROFILE)"
echo "=========================================="
echo ""

# Step 1: Deploy backend
echo "Step 1: Deploying backend (Lambda + API Gateway)..."
aws cloudformation create-stack \
  --stack-name cfn-builder-backend \
  --template-body file://deploy/infrastructure.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=AgentArn,ParameterValue=arn:aws:bedrock-agentcore:us-east-1:905767016260:runtime/mcp_server-CxkrO53RPH

echo "⏳ Waiting for backend deployment (this takes ~2 minutes)..."
aws cloudformation wait stack-create-complete --stack-name cfn-builder-backend

# Get API endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name cfn-builder-backend \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

echo "✅ Backend deployed!"
echo "   API Endpoint: $API_ENDPOINT"
echo ""

# Step 2: Update frontend
echo "Step 2: Updating frontend with API endpoint..."
sed -i.bak "s|http://localhost:3001|$API_ENDPOINT|g" ui/frontend/index.html
rm ui/frontend/index.html.bak

echo "✅ Frontend updated"
echo ""

# Step 3: Initialize git if needed
if [ ! -d ".git" ]; then
    echo "Step 3: Initializing git repository..."
    git init
    git add .
    git commit -m "Initial commit - CloudFormation Builder"
    echo "✅ Git initialized"
else
    echo "Step 3: Git already initialized"
    git add .
    git commit -m "Update API endpoint for production" || echo "No changes to commit"
fi

echo ""
echo "=========================================="
echo "✅ Backend Deployment Complete!"
echo "=========================================="
echo ""
echo "📋 Your API Endpoint:"
echo "   $API_ENDPOINT"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. Push to GitHub:"
echo "   gh repo create cfn-builder --public --source=. --push"
echo "   # Or manually:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/cfn-builder.git"
echo "   git push -u origin main"
echo ""
echo "2. Deploy with AWS Amplify:"
echo "   - Go to: https://console.aws.amazon.com/amplify/"
echo "   - Click 'New app' → 'Host web app'"
echo "   - Select GitHub and your repository"
echo "   - Deploy!"
echo ""
echo "3. Your app will be live at:"
echo "   https://main.YOUR_APP_ID.amplifyapp.com"
echo ""
