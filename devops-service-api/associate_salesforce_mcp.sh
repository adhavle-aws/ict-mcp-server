#!/bin/bash

# Script to associate Salesforce MCP Server with AWS DevOps Agent Space
# Usage: ./associate_salesforce_mcp.sh <agent-space-id> <service-id> [region]

set -e

# Help function
show_help() {
    cat << EOF
Associate Salesforce MCP Server with Agent Space

This script associates a registered Salesforce MCP Server with an AWS DevOps Agent Space.

USAGE:
    $0 <agent-space-id> <service-id> [region]
    $0 --help

PARAMETERS:
    agent-space-id      (Required) The Agent Space ID to associate with
    service-id          (Required) The Service ID from list-services command
    region             (Optional) AWS region (us-east-1 or us-west-2)
                        Default: us-east-1 (recommended)

PREREQUISITES:
    1. AWS CLI must be installed and configured
    2. CloudSmith control plane model must be patched into AWS CLI
    3. Agent Space must already exist
    4. MCP Server must be registered (use register_salesforce_mcp.sh)
    5. Environment variables must be set:
       - AWS_ACCESS_KEY_ID
       - AWS_SECRET_ACCESS_KEY

EXAMPLES:
    # Associate with default region
    $0 "76aca5b7-e9c0-40b7-801d-b881e8d56c72" "1922a9e6-a295-4f8e-b4d1-366df5af3f38"

    # Associate in us-west-2 region
    $0 "76aca5b7-e9c0-40b7-801d-b881e8d56c72" "1922a9e6-a295-4f8e-b4d1-366df5af3f38" us-west-2

    # Show this help message
    $0 --help

EOF
    exit 0
}

# Check for help flag
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
fi

# Check if required parameters are provided
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Error: Missing required parameters"
    echo "Usage: $0 <agent-space-id> <service-id> [region]"
    echo "Run '$0 --help' for more information"
    exit 1
fi

AGENT_SPACE_ID="$1"
SERVICE_ID="$2"
REGION="${3:-us-east-1}"

# Check if AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Error: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set"
    exit 1
fi

# Set endpoint based on region
if [ "$REGION" = "us-west-2" ]; then
    ENDPOINT_URL="https://api.prod.cp.cloudsmith.us-west-2.api.aws"
elif [ "$REGION" = "us-east-1" ]; then
    ENDPOINT_URL="https://api.prod.cp.aidevops.us-east-1.api.aws"
else
    echo "Error: Unsupported region. Use us-east-1 (recommended) or us-west-2"
    exit 1
fi

# Salesforce MCP Server configuration
MCP_NAME="salesforce-mcp-beta"
MCP_ENDPOINT="https://api.salesforce.com/platform/mcp/v1-beta.2/sandbox/sobject-all"
MCP_DESCRIPTION="Salesforce MCP Server - in Beta"

echo "=========================================="
echo "Associating Salesforce MCP Server"
echo "=========================================="
echo "Agent Space ID: $AGENT_SPACE_ID"
echo "Service ID: $SERVICE_ID"
echo "MCP Name: $MCP_NAME"
echo "MCP Endpoint: $MCP_ENDPOINT"
echo "Region: $REGION"
echo "Endpoint: $ENDPOINT_URL"
echo "=========================================="

# Associate the service
echo ""
echo "Associating MCP service with Agent Space..."

# Build the configuration JSON
# Salesforce MCP Server tools
CONFIGURATION=$(cat <<EOF
{
    "mcpserver": {
        "name": "$MCP_NAME",
        "endpoint": "$MCP_ENDPOINT",
        "description": "$MCP_DESCRIPTION",
        "tools": [
            "describe_global",
            "describe_sobject",
            "soql_query",
            "find",
            "list_recent_sobject_records",
            "create_sobject_record",
            "update_sobject_record",
            "delete_sobject_record",
            "get_related_records",
            "update_related_record",
            "delete_related_record",
            "get_user_info"
        ]
    }
}
EOF
)

echo "Debug: Configuration:"
echo "$CONFIGURATION" | jq .
echo ""

set +e
RESPONSE=$(timeout 30 aws cloudsmithcontrolplane associate-service \
    --agent-space-id "$AGENT_SPACE_ID" \
    --service-id "$SERVICE_ID" \
    --configuration "$CONFIGURATION" \
    --endpoint-url "$ENDPOINT_URL" \
    --region "$REGION" \
    --output json 2>&1)
EXIT_CODE=$?
set -e

echo "Exit code: $EXIT_CODE"
echo "Debug: Full Response:"
echo "$RESPONSE"
echo ""

if [ $EXIT_CODE -eq 124 ]; then
    echo "Error: Command timed out after 30 seconds"
    exit 1
fi

if [ $EXIT_CODE -ne 0 ] && ! echo "$RESPONSE" | grep -q "association"; then
    echo "Error: Command failed with exit code $EXIT_CODE"
    exit 1
fi

# Check if there was an error
if echo "$RESPONSE" | grep -q "error occurred"; then
    echo "Error associating MCP service:"
    echo "$RESPONSE"
    exit 1
fi

# Extract association ID
ASSOCIATION_ID=$(echo "$RESPONSE" | jq -r '.association.associationId // .associationId // empty')

if [ -z "$ASSOCIATION_ID" ] || [ "$ASSOCIATION_ID" = "null" ]; then
    echo "Warning: Could not extract association ID, but association may have succeeded"
    echo "Response: $RESPONSE"
fi

echo ""
echo "=========================================="
echo "✓ Salesforce MCP Server associated!"
echo "=========================================="
echo "Agent Space ID: $AGENT_SPACE_ID"
echo "Service ID: $SERVICE_ID"
if [ -n "$ASSOCIATION_ID" ] && [ "$ASSOCIATION_ID" != "null" ]; then
    echo "Association ID: $ASSOCIATION_ID"
fi
echo "Region: $REGION"
echo "=========================================="
echo ""
echo "To verify the association, use:"
echo "aws cloudsmithcontrolplane list-associations \\"
echo "  --agent-space-id $AGENT_SPACE_ID \\"
echo "  --endpoint-url \"$ENDPOINT_URL\" \\"
echo "  --region $REGION"
echo ""
