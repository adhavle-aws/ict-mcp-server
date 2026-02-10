#!/bin/bash

# Script to trigger DevOps Agent investigation for ALB unhealthy targets
# Sends webhook directly (bypasses Lambda)

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
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Trigger ALB Unhealthy Target Investigation (Direct Webhook)

This script sends a webhook directly to the DevOps Agent to investigate
an ALB unhealthy target group issue.

USAGE:
    ./trigger_alb_unhealthy_webhook.sh [target-group] [priority]

PARAMETERS:
    target-group  (Optional) Target group name (default: sfmwcdemov2-tg)
    priority      (Optional) CRITICAL|HIGH|MEDIUM|LOW (default: CRITICAL)

EXAMPLES:
    # Use defaults
    ./trigger_alb_unhealthy_webhook.sh

    # With custom target group
    ./trigger_alb_unhealthy_webhook.sh my-target-group

    # With custom priority
    ./trigger_alb_unhealthy_webhook.sh sfmwcdemov2-tg HIGH

WHAT IT DOES:
    Sends an incident webhook to DevOps Agent with:
    - Event Type: incident
    - Action: created
    - Title: ALB Target Group Unhealthy
    - Description: ALB Target Group <name> is unhealthy
    - Service: alb

WORKFLOW:
    This simulates the CloudWatch Alarm → Lambda → Webhook flow
    by sending the webhook directly to the DevOps Agent.

EOF
    exit 0
fi

# Parse arguments
TARGET_GROUP="${1:-sfmwcdemov2-tg}"
PRIORITY="${2:-CRITICAL}"

# Create timestamp and incident ID
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
INCIDENT_ID="ALB-UNHEALTHY-${TARGET_GROUP}-$(date -u +%Y%m%d%H%M)"

# Create description
DESCRIPTION="ALB Target Group $TARGET_GROUP is unhealthy. Investigate the following: 1) Check target health status and reasons for unhealthy targets. 2) Review recent deployments or configuration changes. 3) Check application logs for errors. 4) Verify security group and network connectivity. 5) Check CloudWatch metrics for UnHealthyHostCount, TargetResponseTime, and HTTPCode_Target_5XX_Count."

echo "=========================================="
echo "ALB Unhealthy Target Investigation"
echo "=========================================="
echo "Target Group: $TARGET_GROUP"
echo "Incident ID: $INCIDENT_ID"
echo "Priority: $PRIORITY"
echo "=========================================="
echo ""

# Create payload
PAYLOAD=$(cat <<EOF | jq -c .
{
  "eventType": "incident",
  "incidentId": "$INCIDENT_ID",
  "action": "created",
  "priority": "$PRIORITY",
  "title": "ALB Target Group $TARGET_GROUP Unhealthy",
  "description": "$DESCRIPTION",
  "service": "alb",
  "timestamp": "$TIMESTAMP",
  "data": {
    "metadata": {
      "target_group": "$TARGET_GROUP",
      "alarm_name": "alb-unhealthy-targets-$TARGET_GROUP",
      "metric": "UnHealthyHostCount",
      "namespace": "AWS/ApplicationELB",
      "source": "cloudwatch_alarm"
    }
  }
}
EOF
)

# Generate HMAC signature
SIGNATURE=$(echo -n "${TIMESTAMP}:${PAYLOAD}" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)

echo "Payload:"
echo "$PAYLOAD" | jq .
echo ""
echo "=========================================="
echo ""

# Send webhook
echo "Sending webhook to DevOps Agent..."
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
echo "Response:"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "202" ]; then
    echo "=========================================="
    echo "✓ Investigation started successfully!"
    echo "=========================================="
    echo "  HTTP Status: $HTTP_STATUS"
    echo "  Incident ID: $INCIDENT_ID"
else
    echo "=========================================="
    echo "✗ Failed to start investigation"
    echo "=========================================="
    echo "  HTTP Status: $HTTP_STATUS"
    exit 1
fi

echo ""
echo "=========================================="
echo "Investigation Details"
echo "=========================================="
echo ""
echo "The DevOps Agent will investigate:"
echo "  - Target health status and failure reasons"
echo "  - Recent deployments or changes"
echo "  - Application logs and errors"
echo "  - Network and security group configuration"
echo "  - CloudWatch metrics (UnHealthyHostCount, etc.)"
echo ""
echo "Check DevOps Agent console for results."
echo "=========================================="
