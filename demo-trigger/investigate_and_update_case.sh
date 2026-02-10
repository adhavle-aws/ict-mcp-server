#!/bin/bash

# Script to investigate a Salesforce case and update it with findings
# Uses a single webhook call with explicit instructions

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

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ] || [ -z "$1" ]; then
    cat << 'EOF'
Investigate Salesforce Case and Update with Findings (Single Request)

This script sends a single investigation request with explicit instructions
to both analyze AND update the Salesforce case.

USAGE:
    ./investigate_and_update_case.sh <case-number> [incident-id] [priority]

PARAMETERS:
    case-number    (Required) Salesforce case number (e.g., 00001124)
    incident-id    (Optional) Custom incident ID 
                   (default: SF-CASE-<case>-YYYYMMDDHHMM)
    priority       (Optional) CRITICAL|HIGH|MEDIUM|LOW (default: HIGH)

DEFAULT INCIDENT ID FORMAT:
    The incident ID is automatically generated as:
    SF-CASE-<case-number>-<timestamp>
    
    Example: SF-CASE-00001124-202602021430
    
    This allows multiple investigations of the same case over time:
    - First investigation:  SF-CASE-00001124-202602021430
    - Second investigation: SF-CASE-00001124-202602021545
    - Next day:            SF-CASE-00001124-202602031020

EXAMPLES:
    # Simple usage
    ./investigate_and_update_case.sh 00001124

    # With custom incident ID
    ./investigate_and_update_case.sh 00001124 INC-2026-001

    # With custom priority
    ./investigate_and_update_case.sh 00001124 INC-2026-001 CRITICAL

WHAT IT DOES:
    Sends a single request with two-part instructions:
    1. ANALYZE: Read and determine root cause of the case
    2. ADD COMMENT: Add a comment to the case with the root cause finding

NOTE:
    This approach includes comment instructions in the initial request,
    which may be more reliable than sending steering as a separate event.

EOF
    exit 0
fi

# Parse arguments
CASE_NUMBER="$1"
INCIDENT_ID="${2:-SF-CASE-${CASE_NUMBER}-$(date -u +%Y%m%d%H%M)}"
PRIORITY="${3:-HIGH}"

# Create comprehensive description - make comment creation the PRIMARY goal
DESCRIPTION="Your PRIMARY TASK is to add a Feedback record to Salesforce case $CASE_NUMBER with root cause findings. To do this: First, investigate case $CASE_NUMBER to determine the root cause. Second, create a FeedItem record for case $CASE_NUMBER with your findings. The FeedItem must have Type='TextPost' and ParentId set to the Case Id. Use the Body field for your root cause analysis. Before you write the final investigation summary, you MUST ALWAYS update the Salesforce case with details of your investigation. Double check that the case is updated before you write the final investigation."

echo "=========================================="
echo "Salesforce Case Investigation & Update"
echo "=========================================="
echo "Case Number: $CASE_NUMBER"
echo "Incident ID: $INCIDENT_ID"
echo "Priority: $PRIORITY"
echo "=========================================="
echo ""
echo "Instructions being sent:"
echo "$DESCRIPTION"
echo ""
echo "=========================================="
echo ""

# Create timestamp and payload with structured metadata
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")

PAYLOAD=$(cat <<EOF | jq -c .
{
"eventType": "incident",
"incidentId": "$INCIDENT_ID",
"action": "created",
"priority": "$PRIORITY",
"title": "Salesforce Case $CASE_NUMBER - Analyze and Update",
"description": "$DESCRIPTION",
"service": "salesforce",
"timestamp": "$TIMESTAMP",
"data": {
"metadata": {
"primary_goal": "create_salesforce_feeditem",
"case_number": "$CASE_NUMBER",
"workflow": [
"investigate_case_for_root_cause",
"create_feeditem_with_findings"
],
"feeditem_requirements": {
"sobject_type": "FeedItem",
"required_fields": {
"Type": "TextPost",
"ParentId": "Case Id from query",
"Body": "Root cause analysis findings"
},
"mandatory": true,
"note": "Use FeedItem not CaseComment for Lightning visibility"
},
"success_criteria": "Task is INCOMPLETE until FeedItem is created in Salesforce",
"reminder": "Do not mark investigation complete until FeedItem is added to Salesforce"
}
}
}
EOF
)

# Generate signature
SIGNATURE=$(echo -n "${TIMESTAMP}:${PAYLOAD}" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)

# Send webhook
echo "Sending investigation request..."
RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
-H "Content-Type: application/json" \
-H "x-amzn-event-timestamp: $TIMESTAMP" \
-H "x-amzn-event-signature: $SIGNATURE" \
-d "$PAYLOAD" \
-w "\nHTTP_STATUS:%{http_code}")

# Parse response
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS")

echo ""
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "202" ]; then
    echo "✓ Investigation request sent successfully!"
    echo "  HTTP Status: $HTTP_STATUS"
    echo "  Response: $BODY"
else
    echo "✗ Failed to send investigation request"
    echo "  HTTP Status: $HTTP_STATUS"
    echo "  Response: $BODY"
    exit 1
fi

echo ""
echo "=========================================="
echo "Investigation started"
echo "=========================================="
echo "The DevOps Agent should now:"
echo "  1. Read and analyze case $CASE_NUMBER"
echo "  2. Determine the root cause"
echo "  3. Add a comment to the case with findings"
echo ""
echo "Check your DevOps Agent console for results."
echo "=========================================="
