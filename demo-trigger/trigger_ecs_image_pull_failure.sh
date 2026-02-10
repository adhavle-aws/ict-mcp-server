#!/bin/bash

# Script to trigger an ECS image pull failure alert
# This creates a CloudWatch alarm by deploying a task with a non-existent image

set -e

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ] || [ -z "$1" ] || [ -z "$2" ]; then
    cat << 'EOF'
Trigger ECS Image Pull Failure Alert

This script triggers a CloudWatch alert by deploying an ECS task definition
with a non-existent Docker image tag, causing image pull failures.

USAGE:
    ./trigger_ecs_image_pull_failure.sh <cluster-name> <service-name> [region]

PARAMETERS:
    cluster-name   (Required) ECS cluster name
    service-name   (Required) ECS service name
    region         (Optional) AWS region (default: us-east-1)

EXAMPLES:
    # Trigger failure in us-east-1
    ./trigger_ecs_image_pull_failure.sh my-cluster my-service

    # Trigger failure in us-west-2
    ./trigger_ecs_image_pull_failure.sh my-cluster my-service us-west-2

WHAT IT DOES:
    1. Gets the current task definition from the service
    2. Creates a modified version with a non-existent image tag
    3. Registers the faulty task definition
    4. Updates the service to use the faulty task definition
    5. This triggers ECS task failures and CloudWatch alarms

REQUIREMENTS:
    - AWS CLI must be installed and configured
    - jq must be installed for JSON processing
    - Appropriate IAM permissions for ECS operations

TO RESTORE SERVICE:
    After testing, you'll need to manually update the service back to
    a working task definition:
    
    aws ecs update-service --cluster <cluster> --service <service> \
      --task-definition <working-task-def-arn>

WARNING:
    This will cause service disruption! Only use in test/demo environments.

EOF
    exit 0
fi

# Parse arguments
CLUSTER_NAME="$1"
SERVICE_NAME="$2"
REGION="${3:-us-east-1}"

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed"
    echo "Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    exit 1
fi

echo "=========================================="
echo "ECS Image Pull Failure Trigger"
echo "=========================================="
echo "Cluster: $CLUSTER_NAME"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
echo "=========================================="
echo ""

# Step 1: Get current task definition
echo "Step 1: Getting current task definition..."
TASK_DEF=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$SERVICE_NAME" \
    --region "$REGION" \
    --query 'services[0].taskDefinition' \
    --output text)

if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" = "None" ]; then
    echo "Error: Could not find task definition for service $SERVICE_NAME in cluster $CLUSTER_NAME"
    exit 1
fi

echo "✓ Current task definition: $TASK_DEF"
echo ""

# Step 2: Create faulty task definition
echo "Step 2: Creating faulty task definition with non-existent image..."
TEMP_FILE="/tmp/faulty-task-def-$(date +%s).json"

aws ecs describe-task-definition \
    --task-definition "$TASK_DEF" \
    --region "$REGION" \
    --query 'taskDefinition' | \
    jq 'del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) |
        .containerDefinitions[0].image = "public.ecr.aws/nginx/nginx:nonexistent-tag-' $(date +%s) '"' \
    > "$TEMP_FILE"

echo "✓ Faulty task definition created at: $TEMP_FILE"
echo ""

# Show the modified image
FAULTY_IMAGE=$(jq -r '.containerDefinitions[0].image' "$TEMP_FILE")
echo "Modified image: $FAULTY_IMAGE"
echo ""

# Step 3: Register faulty task definition
echo "Step 3: Registering faulty task definition..."
FAULTY_TASK_DEF=$(aws ecs register-task-definition \
    --cli-input-json "file://$TEMP_FILE" \
    --region "$REGION" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

if [ -z "$FAULTY_TASK_DEF" ]; then
    echo "Error: Failed to register faulty task definition"
    exit 1
fi

echo "✓ Faulty task definition registered: $FAULTY_TASK_DEF"
echo ""

# Step 4: Update service with faulty task definition
echo "Step 4: Updating service with faulty task definition..."
echo "WARNING: This will cause the service to fail!"
echo ""

aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$SERVICE_NAME" \
    --task-definition "$FAULTY_TASK_DEF" \
    --force-new-deployment \
    --region "$REGION" \
    --output json > /dev/null

echo "✓ Service updated with faulty task definition"
echo ""

# Cleanup temp file
rm -f "$TEMP_FILE"

echo "=========================================="
echo "Image Pull Failure Triggered!"
echo "=========================================="
echo ""
echo "The service will now attempt to pull a non-existent image,"
echo "which will trigger:"
echo "  - ECS task failures"
echo "  - CloudWatch alarms (if configured)"
echo "  - EventBridge events"
echo "  - DevOps Agent investigation (if webhook configured)"
echo ""
echo "Monitor the service:"
echo "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION"
echo ""
echo "View task failures:"
echo "  aws ecs list-tasks --cluster $CLUSTER_NAME --service-name $SERVICE_NAME --region $REGION"
echo ""
echo "=========================================="
echo "TO RESTORE SERVICE:"
echo "=========================================="
echo ""
echo "Update back to the original task definition:"
echo "  aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME \\"
echo "    --task-definition $TASK_DEF --region $REGION"
echo ""
echo "Original task definition: $TASK_DEF"
echo "Faulty task definition: $FAULTY_TASK_DEF"
echo ""
echo "=========================================="
