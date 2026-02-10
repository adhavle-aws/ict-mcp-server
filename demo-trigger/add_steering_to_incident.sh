#!/bin/bash

# Script to add steering instructions to an existing DevOps Agent incident
# This sends an 'updated' action with steering guidance

# Load configuration from .env file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "Error: .env file not found. Please copy .env.example to .env and configure your secrets."
    exit 1
fi

# Use primary webhook configuration
WEBHOOK_URL="${WEBHOOK_URL}"
SECRET="${WEBHOOK_SECRET}"

# Show usage if --help or no arguments
if [ "$1" = "--help" ] || [ "$1" = "-h" ] || [ -z "$1" ]; then
    cat << 'EOF'
Add Steering Instructions to DevOps Agent Incident

This script sends an 'updated' event to add steering instructions to an 
existing incident investigation.

USAGE:
    ./add_steering_to_incident.sh <incident-id> <steering-instructions> [priority]

PARAMETERS:
    incident-id            (Required) The incident ID to update
    steering-instructions  (Required) Instructions for the DevOps Agent
    priority              (Optional) Update priority (default: keeps original)

EXAMPLES:
    # Add Salesforce-specific steering
    ./add_steering_to_incident.sh INC-001 \
      "Use Salesforce MCP tools to query the Account object for records created in the last 24 hours"

    # Add detailed investigation steps
    ./add_steering_to_incident.sh INC-002 \
      "1. Use describe_sobject to check Account schema. 2. Run soql_query to find records with Status='Error'. 3. Check related Opportunity records."

    # Update with new priority
    ./add_steering_to_incident.sh INC-001 \
      "Focus on payment-related Salesforce records only" \
      CRITICAL

    # Add context about recent changes
    ./add_steering_to_incident.sh INC-003 \
      "A Salesforce deployment happened at 10:30 AM. Check for any schema changes to the Contact object that might affect the integration."

WORKFLOW:
    1. Create incident:
       ./trigger_devops_webhook.sh INC-001 created HIGH "API Error" "Salesforce API failing"
    
    2. Add steering as investigation progresses:
       ./add_steering_to_incident.sh INC-001 "Check Salesforce rate limits using get_user_info"
    
    3. Add more context if needed:
       ./add_steering_to_incident.sh INC-001 "Query Opportunity records modified in last hour"
    
    4. Resolve when done:
       ./trigger_devops_webhook.sh INC-001 resolved MEDIUM "Issue resolved"

EOF
    exit 0
fi

# Parse arguments
INCIDENT_ID="$1"
STEERING_INSTRUCTIONS="$2"
PRIORITY="${3:-MEDIUM}"

if [ -z "$INCIDENT_ID" ] || [ -z "$STEERING_INSTRUCTIONS" ]; then
    echo "Error: incident-id and steering-instructions are required"
    echo "Run '$0 --help' for usage information"
    exit 1
fi

# Create timestamp
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")

# Create payload with steering in both description and data fields
PAYLOAD=$(cat <<EOF | jq -c .
{
"eventType": "incident",
"incidentId": "$INCIDENT_ID",
"action": "updated",
"priority": "$PRIORITY",
"title": "Investigation Update - Steering Added",
"description": "Additional investigation guidance: $STEERING_INSTRUCTIONS",
"timestamp": "$TIMESTAMP",
"data": {
  "steering": "$STEERING_INSTRUCTIONS",
  "updateType": "steering",
  "source": "manual",
  "timestamp": "$TIMESTAMP"
}
}
EOF
)

# Generate HMAC signature
SIGNATURE=$(echo -n "${TIMESTAMP}:${PAYLOAD}" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)

# Display what we're sending
echo "=========================================="
echo "Adding Steering to Incident"
echo "=========================================="
echo "Incident ID: $INCIDENT_ID"
echo "Action: updated"
echo "Priority: $PRIORITY"
echo ""
echo "Steering Instructions:"
echo "  $STEERING_INSTRUCTIONS"
echo ""
echo "Timestamp: $TIMESTAMP"
echo "=========================================="
echo ""
echo "Payload:"
echo "$PAYLOAD" | jq .
echo ""
echo "=========================================="
echo ""

# Send webhook
RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
-H "Content-Type: application/json" \
-H "x-amzn-event-timestamp: $TIMESTAMP" \
-H "x-amzn-event-signature: $SIGNATURE" \
-d "$PAYLOAD" \
-w "\nHTTP_STATUS:%{http_code}")

# Parse response
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS")

echo "Response:"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "202" ]; then
    echo "✓ Steering instructions added successfully!"
    echo "  HTTP Status: $HTTP_STATUS"
else
    echo "✗ Failed to add steering instructions"
    echo "  HTTP Status: $HTTP_STATUS"
    exit 1
fi

echo ""
echo "=========================================="
echo "The DevOps Agent will consider these"
echo "instructions in its investigation."
echo "=========================================="
