#!/bin/bash

# Script to generate HTTP traffic against an Application Load Balancer

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Generate ALB Traffic

This script generates continuous HTTP traffic against an Application Load Balancer
to create baseline metrics for investigation testing.

USAGE:
    ./generate_alb_traffic.sh <alb-dns-name> [duration] [requests-per-second]

PARAMETERS:
    alb-dns-name   (Required) ALB DNS name (e.g., sfmwcdemov2-alb-xxx.us-east-1.elb.amazonaws.com)
    duration       (Optional) Duration in seconds (default: 300 = 5 minutes)
    rps            (Optional) Requests per second (default: 2)

EXAMPLES:
    # Run for 5 minutes at 2 requests/second (default)
    ./generate_alb_traffic.sh sfmwcdemov2-alb-xxx.us-east-1.elb.amazonaws.com

    # Run for 10 minutes at 5 requests/second
    ./generate_alb_traffic.sh sfmwcdemov2-alb-xxx.us-east-1.elb.amazonaws.com 600 5

WHAT IT DOES:
    - Sends continuous HTTP GET requests to the ALB
    - Generates RequestCount, TargetResponseTime, and HealthyHostCount metrics
    - Shows success/failure counts
    - Runs in foreground (Ctrl+C to stop early)

REQUIREMENTS:
    - curl must be installed
    - Network access to ALB

EOF
    exit 0
fi

# Parse arguments
ALB_DNS="${1:-sfmwcdemov2-alb-1149431626.us-east-1.elb.amazonaws.com}"
DURATION="${2:-300}"
RPS="${3:-2}"

# Calculate sleep time between requests
SLEEP_TIME=$(echo "scale=3; 1/$RPS" | bc)

echo "=========================================="
echo "ALB Traffic Generator"
echo "=========================================="
echo "ALB DNS: $ALB_DNS"
echo "Duration: $DURATION seconds"
echo "Rate: $RPS requests/second"
echo "=========================================="
echo ""

# Test connection first
echo "Testing ALB connection..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/" --max-time 5)

if [ -z "$HTTP_CODE" ]; then
    echo "✗ Failed to connect to ALB"
    echo "  Check DNS name and network connectivity"
    exit 1
fi

echo "✓ ALB connection successful (HTTP $HTTP_CODE)"
echo ""
echo "Starting traffic generation..."
echo "Press Ctrl+C to stop"
echo ""

START_TIME=$(date +%s)
REQUEST_COUNT=0
SUCCESS_COUNT=0
FAILURE_COUNT=0

# Generate traffic loop
while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    
    if [ $ELAPSED -ge $DURATION ]; then
        break
    fi
    
    # Send HTTP request
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/" --max-time 5)
    REQUEST_COUNT=$((REQUEST_COUNT + 1))
    
    if [ "$HTTP_CODE" = "200" ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi
    
    # Show progress every 10 requests
    if [ $((REQUEST_COUNT % 10)) -eq 0 ]; then
        REMAINING=$((DURATION - ELAPSED))
        SUCCESS_RATE=$(echo "scale=1; $SUCCESS_COUNT * 100 / $REQUEST_COUNT" | bc)
        echo "$(date '+%H:%M:%S') - Requests: $REQUEST_COUNT | Success: $SUCCESS_COUNT | Failed: $FAILURE_COUNT | Success Rate: ${SUCCESS_RATE}% | Time remaining: ${REMAINING}s"
    fi
    
    # Wait before next request
    sleep $SLEEP_TIME
done

echo ""
echo "=========================================="
echo "Traffic generation complete"
echo "=========================================="
echo "Total requests: $REQUEST_COUNT"
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAILURE_COUNT"
SUCCESS_RATE=$(echo "scale=2; $SUCCESS_COUNT * 100 / $REQUEST_COUNT" | bc)
echo "Success rate: ${SUCCESS_RATE}%"
echo "Duration: $ELAPSED seconds"
echo ""
echo "CloudWatch metrics should now show:"
echo "  - RequestCount activity"
echo "  - TargetResponseTime"
echo "  - HTTPCode_Target_2XX_Count"
if [ $FAILURE_COUNT -gt 0 ]; then
    echo "  - HTTPCode_Target_5XX_Count (failures detected)"
fi
echo "=========================================="
