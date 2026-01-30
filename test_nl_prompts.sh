#!/bin/bash
# Test CloudFormation MCP Server with Natural Language Prompts

echo "🧪 Testing CloudFormation MCP Server with Natural Language"
echo "=========================================================="
echo ""

# Test 1: S3 Bucket
echo "Test 1: S3 Bucket with versioning and encryption"
echo "--------------------------------------------------"
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create an S3 bucket with versioning enabled and server-side encryption",
      "format": "yaml"
    }
  }
}'

echo ""
echo ""

# Test 2: Lambda
echo "Test 2: Lambda Function"
echo "-----------------------"
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create a Lambda function with Python 3.11 runtime and IAM execution role",
      "format": "yaml"
    }
  }
}'

echo ""
echo ""

# Test 3: DynamoDB
echo "Test 3: DynamoDB table"
echo "----------------------"
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Create a DynamoDB table with on-demand billing and a partition key named id",
      "format": "yaml"
    }
  }
}'

echo ""
echo ""

# Test 4: Complex 3-tier web application
echo "Test 4: 3-Tier Web Application (Complex)"
echo "-----------------------------------------"
agentcore invoke '{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "build_cfn_template",
    "arguments": {
      "prompt": "Generate a cloudformation template to provision resources to meet requirements outlined in below Q and A. Output should include cloudformation template in <cfn> xml tag, architecture overview, cost optimization tips and quick summary. Q: What kind of application do you want to host? A: It is a 3 tier web application. Q: which aws region do you want the application to be hosted in? A: us-east-1. Q: Any security and/or availability requirements to keep in mind in hosting this application? A: It should be within a private network and highly available",
      "format": "yaml"
    }
  }
}'

echo ""
echo "✅ All tests complete!"
