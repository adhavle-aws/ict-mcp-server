#!/bin/bash

# Script to register Salesforce MCP Server with AWS DevOps Agent Space
# Usage: ./register_salesforce_mcp.sh <agent-space-id> <client-id> <client-secret> [region]

set -e

# Help function
show_help() {
    cat << EOF
Salesforce MCP Server Registration

This script registers a Salesforce MCP Server with an AWS DevOps Agent Space.

USAGE:
    $0 <agent-space-id> <client-id> <client-secret> [region]
    $0 --help

PARAMETERS:
    agent-space-id      (Required) The Agent Space ID to register with
    client-id           (Required) Salesforce OAuth Client ID
    client-secret       (Required) Salesforce OAuth Client Secret
    region             (Optional) AWS region (us-east-1 or us-west-2)
                        Default: us-east-1 (recommended)

PREREQUISITES:
    1. AWS CLI must be installed and configured
    2. CloudSmith control plane model must be patched into AWS CLI
    3. Agent Space must already exist
    4. Environment variables must be set:
       - AWS_ACCESS_KEY_ID
       - AWS_SECRET_ACCESS_KEY

SALESFORCE MCP SERVER CONFIGURATION:
    - Name: salesforce-mcp-beta
    - Endpoint: https://api.salesforce.com/platform/mcp/v1-beta.2/sandbox/sobject-all
    - Description: Salesforce MCP Server - in Beta
    - Flow: OAuth 3LO (3-Legged OAuth)
    - Dynamic Client Registration: Enabled
    - Code Challenge Support: Enabled
    - Scopes: api, sfap_api, refresh_token, einstein_gpt_api, offline_access

EXAMPLES:
    # Register with default region
    $0 "ac7c46ef-4423-4673-b4de-b88728fa3f19" "your-client-id" "your-client-secret"

    # Register in us-west-2 region
    $0 "ac7c46ef-4423-4673-b4de-b88728fa3f19" "your-client-id" "your-client-secret" us-west-2

    # Show this help message
    $0 --help

OUTPUT:
    - Service ID (UUID) will be displayed for future reference
    - Use this Service ID to associate the MCP server with your Agent Space

EOF
    exit 0
}

# Check for help flag
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
fi

# Check if required parameters are provided
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Error: Missing required parameters"
    echo "Usage: $0 <agent-space-id> <client-id> <client-secret> [region]"
    echo "Run '$0 --help' for more information"
    exit 1
fi

AGENT_SPACE_ID="$1"
CLIENT_ID="$2"
CLIENT_SECRET="$3"
REGION="${4:-us-east-1}"

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
EXCHANGE_URL="https://test.salesforce.com/services/oauth2/token"
AUTHORIZATION_URL="https://test.salesforce.com/services/oauth2/authorize"
SCOPES="api,sfap_api,refresh_token,einstein_gpt_api,offline_access"

echo "=========================================="
echo "Registering Salesforce MCP Server"
echo "=========================================="
echo "Agent Space ID: $AGENT_SPACE_ID"
echo "MCP Name: $MCP_NAME"
echo "MCP Endpoint: $MCP_ENDPOINT"
echo "Region: $REGION"
echo "Endpoint: $ENDPOINT_URL"
echo "Flow: OAuth 3LO (3-Legged OAuth)"
echo "Dynamic Client Registration: Enabled"
echo "Code Challenge Support: Enabled"
echo "Scopes: $SCOPES"
echo "=========================================="

# Register the Salesforce MCP service
echo ""
echo "Registering MCP service..."

# Build the service details JSON for MCP server with OAuth 3LO
SERVICE_DETAILS=$(cat <<EOF
{
    "mcpserver": {
        "name": "$MCP_NAME",
        "endpoint": "$MCP_ENDPOINT",
        "description": "$MCP_DESCRIPTION",
        "authorizationConfig": {
            "oAuth3LO": {
                "clientName": "$MCP_NAME",
                "clientId": "$CLIENT_ID",
                "clientSecret": "$CLIENT_SECRET",
                "authorizationUrl": "$AUTHORIZATION_URL",
                "exchangeUrl": "$EXCHANGE_URL",
                "returnToEndpoint": "https://us-east-1.console.aws.amazon.com/",
                "supportCodeChallenge": true,
                "scopes": ["api", "sfap_api", "refresh_token", "einstein_gpt_api", "offline_access"]
            }
        }
    }
}
EOF
)

echo "Debug: Service Details:"
echo "$SERVICE_DETAILS" | jq .
echo ""

RESPONSE=$(aws cloudsmithcontrolplane register-service \
    --service mcpserver \
    --service-details "$SERVICE_DETAILS" \
    --endpoint-url "$ENDPOINT_URL" \
    --region "$REGION" \
    --output json 2>&1)

echo "Debug: Full Response:"
echo "$RESPONSE"
echo ""

# Check if there was an error
if echo "$RESPONSE" | grep -q "error occurred"; then
    echo "Error registering MCP service:"
    echo "$RESPONSE"
    exit 1
fi

# Check if additional OAuth step is required
OAUTH_URL=$(echo "$RESPONSE" | jq -r '.additionalStep.oauth.authorizationUrl // empty')

if [ -n "$OAUTH_URL" ] && [ "$OAUTH_URL" != "null" ]; then
    echo ""
    echo "=========================================="
    echo "OAuth Authorization Required"
    echo "=========================================="
    echo ""
    echo "The MCP server registration requires OAuth 3LO authorization."
    echo "Please complete the OAuth flow by visiting this URL:"
    echo ""
    echo "$OAUTH_URL"
    echo ""
    echo "Steps:"
    echo "1. Copy the URL above and open it in your browser"
    echo "2. Log in to Salesforce and authorize the application"
    echo "3. After authorization, the registration will complete automatically"
    echo "4. You can then check the registration status or list registered services"
    echo ""
    echo "To check registration status later, use:"
    echo "aws cloudsmithcontrolplane list-services \\"
    echo "  --endpoint-url \"$ENDPOINT_URL\" \\"
    echo "  --region $REGION"
    echo ""
    exit 0
fi

# Extract the Service ID
SERVICE_ID=$(echo "$RESPONSE" | jq -r '.serviceId // .service.serviceId // empty')

if [ -z "$SERVICE_ID" ] || [ "$SERVICE_ID" = "null" ]; then
    echo "Error: Failed to extract Service ID"
    echo "Response: $RESPONSE"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ Salesforce MCP Server registered!"
echo "=========================================="
echo "Service ID: $SERVICE_ID"
echo "Agent Space ID: $AGENT_SPACE_ID"
echo "MCP Name: $MCP_NAME"
echo "Region: $REGION"
echo "=========================================="
echo ""
echo "Next step: Associate this service with your Agent Space"
echo ""
echo "Run the following command to associate:"
echo "aws cloudsmithcontrolplane associate-service \\"
echo "  --agent-space-id $AGENT_SPACE_ID \\"
echo "  --service-id $SERVICE_ID \\"
echo "  --configuration '{\"salesforce\": {\"endpoint\": \"$MCP_ENDPOINT\"}}' \\"
echo "  --endpoint-url \"$ENDPOINT_URL\" \\"
echo "  --region $REGION"
echo ""

# Save Service ID to file
echo "$SERVICE_ID" > .salesforce_mcp_service_id
echo "Service ID saved to .salesforce_mcp_service_id"
