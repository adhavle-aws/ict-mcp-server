#!/usr/bin/env bash
# Deploy MCP server to Amazon Bedrock AgentCore Runtime.
# Uses AWS profile aws-gaurav. Git push deploys the frontend to Amplify.

set -e

export AWS_PROFILE=aws-gaurav

echo "🚀 Deploying to AgentCore Runtime (profile: $AWS_PROFILE)"
echo "=========================================="

agentcore launch

echo ""
echo "✅ AgentCore deployment complete."
echo "   Frontend: push to git to deploy via Amplify."
