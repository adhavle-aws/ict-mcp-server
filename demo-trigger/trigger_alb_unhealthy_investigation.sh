#!/bin/bash

# Script to trigger DevOps Agent investigation for ALB unhealthy targets
# This directly invokes the Lambda function with an ALB unhealthy event

set -e

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Trigger ALB Unhealthy Target Investigation

This script directly invokes the Lambda function with an ALB unhealthy target
event to start a DevOps Agent investigation.

USAGE:
    ./trigger_alb_unhealthy_investigation.sh [target-group] [lambda-function] [region]

PARAMETERS:
    target-group    (Optional) Target group name (default: sfmwcdemov2-tg)
    lambda-function (Optional) Lambda function name
                    (default: default-ecs-event-webhook-handler-6bc6189a)
    region          (Optional) AWS region (default: us-east-1)

EXAMPLES:
    # Use all defaults
    ./trigger_alb_unhealthy_investigation.sh

    # With custom target group
    ./trigger_alb_unhealthy_investigation.sh my-target-group

    # With all parameters
    ./trigger_alb_unhealthy_investigation.sh my-tg my-lambda us-west-2

WHAT IT DOES:
    1. Creates a CloudWatch Alarm event for unhealthy ALB targets
    2. Invokes the Lambda function with the event
    3. Lambda starts DevOps Agent investigation with description:
       "ALB Target Group <name> is unhealthy"

REQUIREMENTS:
    - AWS CLI must be installed and configured
    - Appropriate IAM permissions to invoke Lambda functions

EOF
    exit 0
fi

# Parse arguments
TARGET_GROUP="${1:-sfmwcdemov2-tg}"
LAMBDA_FUNCTION="${2:-default-ecs-event-webhook-handler-6bc6189a}"
REGION="${3:-us-east-1}"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "611291728384")

# Generate unique IDs
ALARM_ID="alarm-$(date +%s)"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "=========================================="
echo "ALB Unhealthy Target Investigation"
echo "=========================================="
echo "Target Group: $TARGET_GROUP"
echo "Lambda Function: $LAMBDA_FUNCTION"
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "=========================================="
echo ""

# Create CloudWatch Alarm event payload
# This simulates an alarm state change to ALARM for unhealthy targets
PAYLOAD=$(cat <<EOF
{
  "version": "0",
  "id": "$ALARM_ID",
  "detail-type": "CloudWatch Alarm State Change",
  "source": "aws.cloudwatch",
  "account": "$ACCOUNT_ID",
  "time": "$TIMESTAMP",
  "region": "$REGION",
  "resources": [
    "arn:aws:cloudwatch:$REGION:$ACCOUNT_ID:alarm:alb-unhealthy-targets-$TARGET_GROUP"
  ],
  "detail": {
    "alarmName": "alb-unhealthy-targets-$TARGET_GROUP",
    "state": {
      "value": "ALARM",
      "reason": "Threshold Crossed: 1 datapoint [1.0 ($(date -u +%d/%m/%y %H:%M:%S))] was greater than the threshold (0.0).",
      "reasonData": "{\"version\":\"1.0\",\"queryDate\":\"$TIMESTAMP\",\"startDate\":\"$TIMESTAMP\",\"statistic\":\"Average\",\"period\":60,\"recentDatapoints\":[1.0],\"threshold\":0.0}",
      "timestamp": "$TIMESTAMP"
    },
    "previousState": {
      "value": "OK",
      "reason": "Threshold Crossed: 1 datapoint [0.0 ($(date -u -v-5M +%d/%m/%y %H:%M:%S 2>/dev/null || date -u -d '5 minutes ago' +%d/%m/%y %H:%M:%S))] was not greater than the threshold (0.0).",
      "timestamp": "$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ)"
    },
    "configuration": {
      "description": "ALB Target Group $TARGET_GROUP is unhealthy",
      "metrics": [
        {
          "id": "m1",
          "metricStat": {
            "metric": {
              "namespace": "AWS/ApplicationELB",
              "name": "UnHealthyHostCount",
              "dimensions": {
                "TargetGroup": "targetgroup/$TARGET_GROUP/abc123",
                "LoadBalancer": "app/default-ui/xyz789"
              }
            },
            "period": 60,
            "stat": "Average"
          },
          "returnData": true
        }
      ]
    }
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
TEMP_PAYLOAD="/tmp/alb-alarm-payload-$(date +%s).json"
echo "$PAYLOAD" > "$TEMP_PAYLOAD"

# Create temp file for response
TEMP_RESPONSE="/tmp/alb-alarm-response-$(date +%s).json"

echo "Invoking Lambda function..."
echo ""

# Invoke Lambda function
set +e
aws lambda invoke \
  --function-name "$LAMBDA_FUNCTION" \
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
    echo "Investigation Started"
    echo "=========================================="
    echo ""
    echo "The DevOps Agent should now investigate:"
    echo "  Issue: ALB Target Group $TARGET_GROUP is unhealthy"
    echo "  Priority: CRITICAL"
    echo ""
    echo "Next Steps:"
    echo "=========================================="
    echo ""
    echo "1. Check Lambda logs:"
    echo "   aws logs tail /aws/lambda/$LAMBDA_FUNCTION --follow --region $REGION"
    echo ""
    echo "2. Check DevOps Agent console for investigation"
    echo ""
    echo "3. Monitor CloudWatch for ALB metrics:"
    echo "   - UnHealthyHostCount"
    echo "   - HealthyHostCount"
    echo "   - TargetResponseTime"
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
    echo "  - Verify function name: $LAMBDA_FUNCTION"
    echo "  - Check IAM permissions for lambda:InvokeFunction"
    echo "  - Verify region: $REGION"
    echo ""
fi

# Cleanup
rm -f "$TEMP_PAYLOAD" "$TEMP_RESPONSE"

echo "=========================================="
