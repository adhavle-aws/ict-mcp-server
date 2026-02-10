#!/bin/bash

# Script to create an AWS DevOps Agent Space (CloudSmith AgentSpace)
# Usage: ./create_devops_agent_space.sh <agent-space-name> [description] [region]

set -e

# Help function
show_help() {
    cat << EOF
AWS DevOps Agent Space Creator

This script creates an AWS DevOps Agent Space (CloudSmith AgentSpace) using AWS CLI.

USAGE:
    $0 <agent-space-name> [description] [region]
    $0 --help

PARAMETERS:
    agent-space-name    (Required) Name for the Agent Space
    description         (Optional) Description of the Agent Space
                        Default: "AgentSpace for <agent-space-name>"
    region             (Optional) AWS region (us-east-1 or us-west-2)
                        Default: us-east-1 (recommended)

PREREQUISITES:
    1. AWS CLI must be installed and configured
    2. CloudSmith control plane model must be patched into AWS CLI
    3. Environment variables must be set:
       - AWS_ACCESS_KEY_ID
       - AWS_SECRET_ACCESS_KEY

EXAMPLES:
    # Create with default description and region
    $0 "MyAgentSpace"

    # Create with custom description
    $0 "MyAgentSpace" "Production monitoring agent"

    # Create in us-west-2 region
    $0 "MyAgentSpace" "Dev environment" us-west-2

    # Show this help message
    $0 --help

OUTPUT:
    - Agent Space ID will be displayed and saved to .agent_space_id file
    - Use the Agent Space ID for subsequent CloudSmith operations

NOTES:
    - us-east-1 is the recommended region for new customers
    - The script will fail if AWS credentials are not set
    - Requires jq for JSON parsing

EOF
    exit 0
}

# Check for help flag
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
fi

# Check if agent space name is provided
if [ -z "$1" ]; then
    echo "Error: Agent Space name is required"
    echo "Usage: $0 <agent-space-name> [description] [region]"
    echo "Run '$0 --help' for more information"
    exit 1
fi

AGENT_SPACE_NAME="$1"
DESCRIPTION="${2:-AgentSpace for $AGENT_SPACE_NAME}"
REGION="${3:-us-east-1}"

# Check if AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Error: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set"
    exit 1
fi

# Set endpoint based on region
if [ "$REGION" = "us-west-2" ]; then
    ENDPOINT_URL="https://api.prod.cp.cloudsmith.us-west-2.api.aws"
    SERVICE_NAME="cloudsmith"
elif [ "$REGION" = "us-east-1" ]; then
    ENDPOINT_URL="https://api.prod.cp.aidevops.us-east-1.api.aws"
    SERVICE_NAME="aidevops"
else
    echo "Error: Unsupported region. Use us-east-1 (recommended) or us-west-2"
    exit 1
fi

echo "=========================================="
echo "Creating AWS DevOps Agent Space"
echo "=========================================="
echo "Name: $AGENT_SPACE_NAME"
echo "Description: $DESCRIPTION"
echo "Region: $REGION"
echo "Endpoint: $ENDPOINT_URL"
echo "=========================================="

# Create the Agent Space
echo ""
echo "Creating Agent Space..."
RESPONSE=$(aws cloudsmithcontrolplane create-agent-space \
    --name "$AGENT_SPACE_NAME" \
    --description "$DESCRIPTION" \
    --endpoint-url "$ENDPOINT_URL" \
    --region "$REGION" \
    --output json 2>&1)

# Check if there was an error
if echo "$RESPONSE" | grep -q "error occurred"; then
    echo "Error creating Agent Space:"
    echo "$RESPONSE"
    exit 1
fi

# Extract and display the Agent Space ID
AGENT_SPACE_ID=$(echo "$RESPONSE" | jq -r '.agentSpace.agentSpaceId // .agentSpaceId // empty')

if [ -z "$AGENT_SPACE_ID" ] || [ "$AGENT_SPACE_ID" = "null" ]; then
    echo "Error: Failed to extract Agent Space ID"
    echo "Response: $RESPONSE"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ Agent Space created successfully!"
echo "=========================================="
echo "Agent Space ID: $AGENT_SPACE_ID"
echo "Name: $AGENT_SPACE_NAME"
echo "Region: $REGION"
echo "=========================================="
echo ""
echo "Save this Agent Space ID for future operations:"
echo "export AGENT_SPACE_ID=$AGENT_SPACE_ID"
echo ""

# Save to file for reference
echo "$AGENT_SPACE_ID" > .agent_space_id
echo "Agent Space ID saved to .agent_space_id"
