#!/bin/bash

# Script to setup CloudWatch alarm for ALB unhealthy target group
# This alarm will trigger the Lambda function when targets become unhealthy

set -e

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Setup ALB Unhealthy Target Group Alarm

This script creates a CloudWatch alarm that monitors the ALB target group
for unhealthy targets and triggers the Lambda function for DevOps investigation.

USAGE:
    ./setup_alb_unhealthy_alarm.sh [target-group-name] [lambda-function] [region]

PARAMETERS:
    target-group-name  (Optional) Target group name 
                       (default: sfmwcdemov2-tg)
    lambda-function    (Optional) Lambda function name
                       (default: default-ecs-event-webhook-handler-6bc6189a)
    region            (Optional) AWS region (default: us-east-1)

EXAMPLES:
    # Use all defaults
    ./setup_alb_unhealthy_alarm.sh

    # With custom target group
    ./setup_alb_unhealthy_alarm.sh my-target-group

    # With all parameters
    ./setup_alb_unhealthy_alarm.sh my-tg my-lambda us-west-2

WHAT IT DOES:
    1. Gets the target group ARN
    2. Gets the load balancer ARN
    3. Creates an SNS topic for alarm notifications
    4. Subscribes the Lambda function to the SNS topic
    5. Creates a CloudWatch alarm for UnHealthyHostCount > 0
    6. Grants SNS permission to invoke Lambda

REQUIREMENTS:
    - AWS CLI must be installed and configured
    - jq must be installed for JSON processing
    - Appropriate IAM permissions

EOF
    exit 0
fi

# Parse arguments
TARGET_GROUP_NAME="${1:-sfmwcdemov2-tg}"
LAMBDA_FUNCTION="${2:-default-ecs-event-webhook-handler-6bc6189a}"
REGION="${3:-us-east-1}"

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed"
    echo "Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    exit 1
fi

echo "=========================================="
echo "ALB Unhealthy Target Alarm Setup"
echo "=========================================="
echo "Target Group: $TARGET_GROUP_NAME"
echo "Lambda Function: $LAMBDA_FUNCTION"
echo "Region: $REGION"
echo "=========================================="
echo ""

# Step 1: Get target group ARN
echo "Step 1: Getting target group ARN..."
TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
    --names "$TARGET_GROUP_NAME" \
    --region "$REGION" \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text 2>/dev/null)

if [ -z "$TARGET_GROUP_ARN" ] || [ "$TARGET_GROUP_ARN" = "None" ]; then
    echo "Error: Target group '$TARGET_GROUP_NAME' not found"
    echo ""
    echo "Available target groups:"
    aws elbv2 describe-target-groups --region "$REGION" --query 'TargetGroups[*].TargetGroupName' --output table
    exit 1
fi

echo "✓ Target Group ARN: $TARGET_GROUP_ARN"

# Extract target group suffix for CloudWatch dimensions
TG_SUFFIX=$(echo "$TARGET_GROUP_ARN" | sed 's/.*targetgroup\///')
echo "  Target Group Suffix: $TG_SUFFIX"
echo ""

# Step 2: Get load balancer ARN
echo "Step 2: Getting load balancer ARN..."
LB_ARN=$(aws elbv2 describe-target-groups \
    --names "$TARGET_GROUP_NAME" \
    --region "$REGION" \
    --query 'TargetGroups[0].LoadBalancerArns[0]' \
    --output text 2>/dev/null)

if [ -z "$LB_ARN" ] || [ "$LB_ARN" = "None" ]; then
    echo "Warning: No load balancer associated with target group"
    LB_SUFFIX=""
else
    echo "✓ Load Balancer ARN: $LB_ARN"
    LB_SUFFIX=$(echo "$LB_ARN" | sed 's/.*loadbalancer\///')
    echo "  Load Balancer Suffix: $LB_SUFFIX"
fi
echo ""

# Step 3: Create SNS topic
echo "Step 3: Creating SNS topic for alarm notifications..."
SNS_TOPIC_NAME="alb-unhealthy-targets-alert"

SNS_TOPIC_ARN=$(aws sns create-topic \
    --name "$SNS_TOPIC_NAME" \
    --region "$REGION" \
    --query 'TopicArn' \
    --output text 2>/dev/null)

if [ -z "$SNS_TOPIC_ARN" ]; then
    echo "Error: Failed to create SNS topic"
    exit 1
fi

echo "✓ SNS Topic ARN: $SNS_TOPIC_ARN"
echo ""

# Step 4: Get Lambda function ARN
echo "Step 4: Getting Lambda function ARN..."
LAMBDA_ARN=$(aws lambda get-function \
    --function-name "$LAMBDA_FUNCTION" \
    --region "$REGION" \
    --query 'Configuration.FunctionArn' \
    --output text 2>/dev/null)

if [ -z "$LAMBDA_ARN" ]; then
    echo "Error: Lambda function '$LAMBDA_FUNCTION' not found"
    exit 1
fi

echo "✓ Lambda ARN: $LAMBDA_ARN"
echo ""

# Step 5: Subscribe Lambda to SNS topic
echo "Step 5: Subscribing Lambda to SNS topic..."
SUBSCRIPTION_ARN=$(aws sns subscribe \
    --topic-arn "$SNS_TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint "$LAMBDA_ARN" \
    --region "$REGION" \
    --query 'SubscriptionArn' \
    --output text 2>/dev/null)

echo "✓ Subscription ARN: $SUBSCRIPTION_ARN"
echo ""

# Step 6: Grant SNS permission to invoke Lambda
echo "Step 6: Granting SNS permission to invoke Lambda..."
aws lambda add-permission \
    --function-name "$LAMBDA_FUNCTION" \
    --statement-id "AllowSNSInvoke-$(date +%s)" \
    --action "lambda:InvokeFunction" \
    --principal sns.amazonaws.com \
    --source-arn "$SNS_TOPIC_ARN" \
    --region "$REGION" \
    --output text > /dev/null 2>&1 || echo "  (Permission may already exist)"

echo "✓ Lambda permission granted"
echo ""

# Step 7: Create CloudWatch alarm
echo "Step 7: Creating CloudWatch alarm..."
ALARM_NAME="alb-unhealthy-targets-$TARGET_GROUP_NAME"

# Build dimensions based on whether we have a load balancer
if [ -n "$LB_SUFFIX" ]; then
    DIMENSIONS="Name=TargetGroup,Value=$TG_SUFFIX Name=LoadBalancer,Value=$LB_SUFFIX"
else
    DIMENSIONS="Name=TargetGroup,Value=$TG_SUFFIX"
fi

aws cloudwatch put-metric-alarm \
    --alarm-name "$ALARM_NAME" \
    --alarm-description "ALB Target Group $TARGET_GROUP_NAME is unhealthy" \
    --actions-enabled \
    --alarm-actions "$SNS_TOPIC_ARN" \
    --metric-name UnHealthyHostCount \
    --namespace AWS/ApplicationELB \
    --statistic Average \
    --dimensions $DIMENSIONS \
    --period 60 \
    --evaluation-periods 1 \
    --threshold 0 \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --region "$REGION"

echo "✓ CloudWatch alarm created: $ALARM_NAME"
echo ""

echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Configuration Summary:"
echo "  Target Group: $TARGET_GROUP_NAME"
echo "  Alarm Name: $ALARM_NAME"
echo "  SNS Topic: $SNS_TOPIC_ARN"
echo "  Lambda Function: $LAMBDA_FUNCTION"
echo ""
echo "The alarm will trigger when:"
echo "  - UnHealthyHostCount > 0 for 1 minute"
echo "  - SNS will notify the Lambda function"
echo "  - Lambda will start DevOps investigation with:"
echo "    'ALB Target Group $TARGET_GROUP_NAME is unhealthy'"
echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Test the alarm by making targets unhealthy"
echo "2. Monitor CloudWatch alarm state:"
echo "   aws cloudwatch describe-alarms --alarm-names $ALARM_NAME --region $REGION"
echo ""
echo "3. View Lambda logs:"
echo "   aws logs tail /aws/lambda/$LAMBDA_FUNCTION --follow --region $REGION"
echo ""
echo "4. Check DevOps Agent console for investigation"
echo ""
echo "=========================================="
