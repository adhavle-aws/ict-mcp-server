#!/bin/bash

# Script to trigger ALB unhealthy target alarm by simulating alarm state
# This is for demo purposes to test the DevOps Agent investigation workflow

set -e

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Trigger ALB Unhealthy Target Alarm

This script triggers the CloudWatch alarm by setting it to ALARM state,
which will invoke the Lambda function and start a DevOps investigation.

USAGE:
    ./trigger_alb_unhealthy_alarm.sh [alarm-name] [region]

PARAMETERS:
    alarm-name  (Optional) CloudWatch alarm name
                (default: alb-unhealthy-targets-sfmwcdemov2-tg)
    region      (Optional) AWS region (default: us-east-1)

EXAMPLES:
    # Use defaults
    ./trigger_alb_unhealthy_alarm.sh

    # With custom alarm name
    ./trigger_alb_unhealthy_alarm.sh my-alarm-name

    # With all parameters
    ./trigger_alb_unhealthy_alarm.sh my-alarm us-west-2

WHAT IT DOES:
    1. Sets the CloudWatch alarm to ALARM state
    2. This triggers the SNS notification
    3. SNS invokes the Lambda function
    4. Lambda starts DevOps Agent investigation

NOTE:
    This uses set-alarm-state for demo purposes. In production,
    the alarm would be triggered by actual unhealthy targets.

REQUIREMENTS:
    - AWS CLI must be installed and configured
    - CloudWatch alarm must already exist (run setup_alb_unhealthy_alarm.sh first)
    - Appropriate IAM permissions

EOF
    exit 0
fi

# Parse arguments
ALARM_NAME="${1:-alb-unhealthy-targets-sfmwcdemov2-tg}"
REGION="${2:-us-east-1}"

echo "=========================================="
echo "Trigger ALB Unhealthy Target Alarm"
echo "=========================================="
echo "Alarm Name: $ALARM_NAME"
echo "Region: $REGION"
echo "=========================================="
echo ""

# Check if alarm exists
echo "Checking if alarm exists..."
ALARM_EXISTS=$(aws cloudwatch describe-alarms \
    --alarm-names "$ALARM_NAME" \
    --region "$REGION" \
    --query 'MetricAlarms[0].AlarmName' \
    --output text 2>/dev/null)

if [ -z "$ALARM_EXISTS" ] || [ "$ALARM_EXISTS" = "None" ]; then
    echo "Error: Alarm '$ALARM_NAME' not found"
    echo ""
    echo "Available alarms:"
    aws cloudwatch describe-alarms --region "$REGION" --query 'MetricAlarms[*].AlarmName' --output table
    echo ""
    echo "Run setup_alb_unhealthy_alarm.sh first to create the alarm"
    exit 1
fi

echo "✓ Alarm exists"
echo ""

# Get current alarm state
CURRENT_STATE=$(aws cloudwatch describe-alarms \
    --alarm-names "$ALARM_NAME" \
    --region "$REGION" \
    --query 'MetricAlarms[0].StateValue' \
    --output text)

echo "Current alarm state: $CURRENT_STATE"
echo ""

# Set alarm to ALARM state
echo "Setting alarm to ALARM state..."
echo "This will trigger the Lambda function and start DevOps investigation..."
echo ""

aws cloudwatch set-alarm-state \
    --alarm-name "$ALARM_NAME" \
    --state-value ALARM \
    --state-reason "Manual trigger for DevOps Agent demo - ALB Target Group sfmwcdemov2-tg is unhealthy" \
    --region "$REGION"

echo "✓ Alarm state set to ALARM"
echo ""

# Wait a moment for processing
echo "Waiting for alarm to trigger..."
sleep 3
echo ""

echo "=========================================="
echo "✓ Alarm Triggered!"
echo "=========================================="
echo ""
echo "The alarm has been set to ALARM state, which should:"
echo "  1. Send notification to SNS topic"
echo "  2. SNS invokes Lambda function"
echo "  3. Lambda processes the alarm and sends to webhook"
echo "  4. DevOps Agent starts investigation with description:"
echo "     'ALB Target Group sfmwcdemov2-tg is unhealthy'"
echo ""
echo "=========================================="
echo "Monitor the Investigation:"
echo "=========================================="
echo ""
echo "1. Check alarm state:"
echo "   aws cloudwatch describe-alarms --alarm-names $ALARM_NAME --region $REGION"
echo ""
echo "2. View Lambda logs:"
echo "   aws logs tail /aws/lambda/default-ecs-event-webhook-handler-6bc6189a --follow --region $REGION"
echo ""
echo "3. Check DevOps Agent console for investigation"
echo ""
echo "4. To reset alarm to OK state:"
echo "   aws cloudwatch set-alarm-state --alarm-name $ALARM_NAME --state-value OK --state-reason 'Reset after demo' --region $REGION"
echo ""
echo "=========================================="
