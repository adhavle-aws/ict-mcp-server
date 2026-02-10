# ALB Unhealthy Target Alarm Demo

This demo shows how CloudWatch alarms automatically trigger DevOps Agent investigations when ALB targets become unhealthy.

## Architecture

```
CloudWatch Alarm (UnHealthyHostCount > 0)
    ↓
SNS Topic (alb-unhealthy-targets-alert)
    ↓
Lambda Function (default-ecs-event-webhook-handler-6bc6189a)
    ↓
DevOps Agent Webhook
    ↓
Investigation: "ALB Target Group sfmwcdemov2-tg is unhealthy"
```

## Components

### 1. CloudWatch Alarm
- **Name**: `alb-unhealthy-targets-sfmwcdemov2-tg`
- **Metric**: `AWS/ApplicationELB` → `UnHealthyHostCount`
- **Threshold**: > 0 for 1 minute
- **Target Group**: `sfmwcdemov2-tg`
- **Load Balancer**: `sfmwcdemov2-alb`

### 2. SNS Topic
- **ARN**: `arn:aws:sns:us-east-1:611291728384:alb-unhealthy-targets-alert`
- **Subscriber**: Lambda function

### 3. Lambda Function
- **Name**: `default-ecs-event-webhook-handler-6bc6189a`
- **Capabilities**: 
  - Handles ECS events from EventBridge
  - Handles CloudWatch alarms from SNS
  - Transforms events to incident payloads
  - Sends to DevOps Agent webhook

### 4. DevOps Agent Webhook
- **URL**: Configured in `demo-trigger/.env`
- **Authentication**: HMAC signature

## Setup (One-Time)

The setup has already been completed, but here's what was done:

```bash
./demo-trigger/setup_alb_unhealthy_alarm.sh
```

This script:
1. ✅ Created CloudWatch alarm for unhealthy targets
2. ✅ Created SNS topic for notifications
3. ✅ Subscribed Lambda function to SNS topic
4. ✅ Granted SNS permission to invoke Lambda
5. ✅ Updated Lambda code to handle CloudWatch alarms

## Demo Steps

### Option 1: Manual Alarm Trigger (Recommended)

This is the most reliable method for demos:

```bash
# Trigger the alarm
./demo-trigger/trigger_alb_unhealthy_alarm.sh
```

**What happens:**
1. Alarm state changes from OK → ALARM
2. SNS sends notification to Lambda
3. Lambda transforms alarm to incident payload
4. DevOps Agent receives webhook and starts investigation

**Monitor the investigation:**
```bash
# View Lambda logs
aws logs tail /aws/lambda/default-ecs-event-webhook-handler-6bc6189a --follow --region us-east-1

# Check alarm state
aws cloudwatch describe-alarms --alarm-names alb-unhealthy-targets-sfmwcdemov2-tg --region us-east-1
```

**Reset after demo:**
```bash
aws cloudwatch set-alarm-state \
  --alarm-name alb-unhealthy-targets-sfmwcdemov2-tg \
  --state-value OK \
  --state-reason 'Reset after demo' \
  --region us-east-1
```

### Option 2: Direct Webhook (Bypass Lambda)

Send webhook directly to DevOps Agent:

```bash
./demo-trigger/trigger_alb_unhealthy_webhook.sh
```

This bypasses CloudWatch and Lambda entirely, useful for testing the DevOps Agent directly.

### Option 3: Real Unhealthy Targets (Advanced)

Make targets actually unhealthy to trigger the alarm naturally:

**Step 1: Break the health check**
```bash
# Change health check to a non-existent path
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:611291728384:targetgroup/sfmwcdemov2-tg/3168f6e2cf7339e8 \
  --health-check-path /this-does-not-exist \
  --region us-east-1
```

**Step 2: Generate traffic** (required for CloudWatch metrics)
```bash
./demo-trigger/generate_alb_traffic.sh sfmwcdemov2-alb-1149431626.us-east-1.elb.amazonaws.com 120 2
```

**Step 3: Wait for alarm** (1-2 minutes)
```bash
# Monitor alarm state
watch -n 10 'aws cloudwatch describe-alarms --alarm-names alb-unhealthy-targets-sfmwcdemov2-tg --region us-east-1 --query "MetricAlarms[0].StateValue" --output text'
```

**Step 4: Restore health check**
```bash
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:611291728384:targetgroup/sfmwcdemov2-tg/3168f6e2cf7339e8 \
  --health-check-path / \
  --region us-east-1
```

**Note:** Option 3 requires active traffic to the ALB for CloudWatch to publish metrics. Option 1 is more reliable for demos.

## Verification

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/default-ecs-event-webhook-handler-6bc6189a --since 5m --region us-east-1
```

Look for:
- `incident_id: cloudwatch-alarm:alb-unhealthy-targets-sfmwcdemov2-tg:...`
- `Webhook delivery successful`
- `status_code: 200`
- `priority: CRITICAL`

### Check Target Health
```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:611291728384:targetgroup/sfmwcdemov2-tg/3168f6e2cf7339e8 \
  --region us-east-1 \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State,TargetHealth.Reason]' \
  --output table
```

### Check Alarm State
```bash
aws cloudwatch describe-alarms \
  --alarm-names alb-unhealthy-targets-sfmwcdemov2-tg \
  --region us-east-1 \
  --query 'MetricAlarms[0].[StateValue,StateReason,StateUpdatedTimestamp]' \
  --output table
```

## Troubleshooting

### Alarm doesn't trigger with real unhealthy targets
- **Cause**: CloudWatch only publishes UnHealthyHostCount when there's active traffic
- **Solution**: Use `generate_alb_traffic.sh` to send requests to the ALB

### Lambda not invoked
- **Check**: SNS subscription is active
  ```bash
  aws sns list-subscriptions-by-topic \
    --topic-arn arn:aws:sns:us-east-1:611291728384:alb-unhealthy-targets-alert \
    --region us-east-1
  ```
- **Check**: Lambda has permission from SNS
  ```bash
  aws lambda get-policy \
    --function-name default-ecs-event-webhook-handler-6bc6189a \
    --region us-east-1
  ```

### Webhook delivery fails (403 error)
- **Check**: HMAC secret in Secrets Manager matches DevOps Agent
  ```bash
  aws secretsmanager get-secret-value \
    --secret-id arn:aws:secretsmanager:us-east-1:611291728384:secret:ecs-event-webhook/hmac-key-glwwwZ \
    --region us-east-1 \
    --query SecretString \
    --output text
  ```
- **Expected**: `5oEhntph6fBbuOXX0fC00INRW95OEQj84vBPXOHcDhc=`

## Demo Script

Here's a complete demo flow:

```bash
# 1. Show the alarm configuration
echo "=== CloudWatch Alarm Configuration ==="
aws cloudwatch describe-alarms \
  --alarm-names alb-unhealthy-targets-sfmwcdemov2-tg \
  --region us-east-1

# 2. Show current target health (should be healthy)
echo "=== Current Target Health ==="
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:611291728384:targetgroup/sfmwcdemov2-tg/3168f6e2cf7339e8 \
  --region us-east-1

# 3. Trigger the alarm
echo "=== Triggering Alarm ==="
./demo-trigger/trigger_alb_unhealthy_alarm.sh

# 4. Show Lambda logs (in another terminal)
aws logs tail /aws/lambda/default-ecs-event-webhook-handler-6bc6189a --follow --region us-east-1

# 5. Show DevOps Agent console
# Navigate to DevOps Agent UI and show the investigation

# 6. Reset alarm
echo "=== Resetting Alarm ==="
aws cloudwatch set-alarm-state \
  --alarm-name alb-unhealthy-targets-sfmwcdemov2-tg \
  --state-value OK \
  --state-reason 'Demo complete' \
  --region us-east-1
```

## Related Scripts

- `setup_alb_unhealthy_alarm.sh` - One-time setup (already completed)
- `trigger_alb_unhealthy_alarm.sh` - Manual alarm trigger (recommended)
- `trigger_alb_unhealthy_webhook.sh` - Direct webhook (bypass Lambda)
- `generate_alb_traffic.sh` - Generate ALB traffic for metrics
- `trigger_lambda_ecs_event.sh` - Test ECS event handling
- `trigger_ecs_image_pull_failure.sh` - Cause ECS task failures

## Key Takeaways

1. ✅ CloudWatch alarms can automatically trigger DevOps Agent investigations
2. ✅ Lambda handles both ECS events and CloudWatch alarms
3. ✅ SNS provides reliable notification delivery
4. ✅ Manual triggers are more reliable for demos than real failures
5. ✅ The complete workflow is: Alarm → SNS → Lambda → Webhook → Investigation
