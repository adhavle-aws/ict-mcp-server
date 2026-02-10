#!/bin/bash

# Script to trigger Lambda function with ECS Task State Change event
# This simulates an ECS task failure event for demo purposes

set -e

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Trigger Lambda with ECS Task State Change Event

This script invokes a Lambda function with a simulated ECS Task State Change
event to trigger DevOps Agent investigation.

USAGE:
    ./trigger_lambda_ecs_event.sh [function-name] [cluster] [service] [region]

PARAMETERS:
    function-name  (Optional) Lambda function name 
                   (default: default-ecs-event-webhook-handler-6bc6189a)
    cluster        (Optional) ECS cluster name (default: my-cluster)
    service        (Optional) ECS service name (default: my-service)
    region         (Optional) AWS region (default: us-east-1)

EXAMPLES:
    # Use defaults (recommended for demo)
    ./trigger_lambda_ecs_event.sh

    # With custom cluster and service
    ./trigger_lambda_ecs_event.sh default-ecs-event-webhook-handler-6bc6189a prod-cluster api-service

    # With all parameters
    ./trigger_lambda_ecs_event.sh my-function prod-cluster api-service us-west-2

WHAT IT DOES:
    1. Creates an ECS Task State Change event payload
    2. Invokes the Lambda function with the event
    3. Shows the Lambda response
    4. This should trigger the DevOps Agent investigation workflow

EVENT DETAILS:
    - Event Type: ECS Task State Change
    - Status: STOPPED (task failure)
    - Stop Code: EssentialContainerExited
    - Reason: Essential container exited

REQUIREMENTS:
    - AWS CLI must be installed and configured
    - Appropriate IAM permissions to invoke Lambda functions

EOF
    exit 0
fi

# Parse arguments
FUNCTION_NAME="${1:-default-ecs-event-webhook-handler-6bc6189a}"
CLUSTER_NAME="${2:-my-cluster}"
SERVICE_NAME="${3:-my-service}"
REGION="${4:-us-east-1}"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "123456789012")

# Generate unique IDs
EVENT_ID="test-event-$(date +%s)"
TASK_ID="task-$(date +%s)"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CREATED_AT=$(date -u -v-5M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d '5 minutes ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "2025-01-07T11:55:00Z")

echo "=========================================="
echo "Lambda ECS Event Trigger"
echo "=========================================="
echo "Function: $FUNCTION_NAME"
echo "Cluster: $CLUSTER_NAME"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "=========================================="
echo ""

# Create the event payload
PAYLOAD=$(cat <<EOF
{
  "version": "0",
  "id": "$EVENT_ID",
  "detail-type": "ECS Task State Change",
  "source": "aws.ecs",
  "account": "$ACCOUNT_ID",
  "time": "$TIMESTAMP",
  "region": "$REGION",
  "resources": [
    "arn:aws:ecs:$REGION:$ACCOUNT_ID:task/$CLUSTER_NAME/$TASK_ID"
  ],
  "detail": {
    "clusterArn": "arn:aws:ecs:$REGION:$ACCOUNT_ID:cluster/$CLUSTER_NAME",
    "taskArn": "arn:aws:ecs:$REGION:$ACCOUNT_ID:task/$CLUSTER_NAME/$TASK_ID",
    "lastStatus": "STOPPED",
    "desiredStatus": "STOPPED",
    "stopCode": "EssentialContainerExited",
    "stoppedReason": "Essential container exited",
    "group": "service:$SERVICE_NAME",
    "createdAt": "$CREATED_AT",
    "stoppedAt": "$TIMESTAMP",
    "version": 1
  }
}
EOF
)

echo "Event Payload:"
echo "$PAYLOAD" | jq .
echo ""
echo "=========================================="
echo ""

# Create temp file for payload
TEMP_PAYLOAD="/tmp/lambda-payload-$(date +%s).json"
echo "$PAYLOAD" > "$TEMP_PAYLOAD"

# Create temp file for response
TEMP_RESPONSE="/tmp/lambda-response-$(date +%s).json"

echo "Invoking Lambda function..."
echo ""

# Invoke Lambda function
set +e
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --cli-binary-format raw-in-base64-out \
  --payload "file://$TEMP_PAYLOAD" \
  --region "$REGION" \
  "$TEMP_RESPONSE"

INVOKE_EXIT_CODE=$?
set -e

echo ""

if [ $INVOKE_EXIT_CODE -eq 0 ]; then
    echo "=========================================="
    echo "✓ Lambda invoked successfully!"
    echo "=========================================="
    echo ""
    
    if [ -f "$TEMP_RESPONSE" ]; then
        echo "Lambda Response:"
        cat "$TEMP_RESPONSE" | jq . 2>/dev/null || cat "$TEMP_RESPONSE"
        echo ""
    fi
    
    echo "=========================================="
    echo "Next Steps:"
    echo "=========================================="
    echo ""
    echo "1. Check Lambda logs:"
    echo "   aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"
    echo ""
    echo "2. Check DevOps Agent console for investigation"
    echo ""
    echo "3. Monitor CloudWatch for alerts"
    echo ""
else
    echo "=========================================="
    echo "✗ Lambda invocation failed"
    echo "=========================================="
    echo ""
    echo "Exit code: $INVOKE_EXIT_CODE"
    echo ""
    
    if [ -f "$TEMP_RESPONSE" ]; then
        echo "Error response:"
        cat "$TEMP_RESPONSE"
        echo ""
    fi
    
    echo "Troubleshooting:"
    echo "  - Verify function name: $FUNCTION_NAME"
    echo "  - Check IAM permissions for lambda:InvokeFunction"
    echo "  - Verify region: $REGION"
    echo ""
fi

# Cleanup
rm -f "$TEMP_PAYLOAD" "$TEMP_RESPONSE"

echo "=========================================="
