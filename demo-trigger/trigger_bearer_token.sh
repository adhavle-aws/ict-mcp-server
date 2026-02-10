#!/bin/bash

# Load configuration from .env file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "Error: .env file not found. Please copy .env.example to .env and configure your secrets."
    exit 1
fi

# Use bearer token webhook configuration (if available, otherwise use primary)
WEBHOOK_URL="${WEBHOOK_URL_BEARER:-$WEBHOOK_URL}"
SECRET="${WEBHOOK_SECRET_BEARER:-$WEBHOOK_SECRET}"

# Create payload
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
INCIDENT_ID="test-alert-$(date +%s)"

PAYLOAD=$(cat <<EOF
{
"eventType": "incident",
"incidentId": "$INCIDENT_ID",
"action": "created",
"priority": "HIGH",
"title": "Test Alert",
"description": "Test alert description",
"service": "TestService",
"timestamp": "$TIMESTAMP"
}
EOF
)

# Generate HMAC signature
SIGNATURE=$(echo -n "${TIMESTAMP}:${PAYLOAD}" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)

# Send webhook
echo "Timestamp: $TIMESTAMP"
echo "Signature: $SIGNATURE"
echo "Payload: $PAYLOAD"
echo ""
curl -v -X POST "$WEBHOOK_URL" \
-H "Content-Type: application/json" \
-H "x-amzn-event-timestamp: $TIMESTAMP" \
-H "x-amzn-event-signature: $SIGNATURE" \
-d "$PAYLOAD"
