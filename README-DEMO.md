# AWS DevOps Agent Demo - Automated Incident Investigation

This guide demonstrates how to use the AWS DevOps Agent to automatically investigate AWS infrastructure incidents and update Salesforce cases with findings.

## Overview

The demo simulates a real-world incident scenario:
1. Generate baseline traffic to an Application Load Balancer
2. Simulate an outage by stopping an EC2 instance
3. Automatically investigate the incident using AWS DevOps Agent
4. Post root cause analysis to Salesforce case

## Prerequisites

- AWS CLI configured with credentials
- Access to AWS account 611291728384 (us-east-1)
- Salesforce case management access
- `curl` installed (for traffic generation)
- `jq` installed (for JSON processing)

## Architecture

**Infrastructure:**
- Application Load Balancer: `sfmwcdemov2-alb-1149431626.us-east-1.elb.amazonaws.com`
- EC2 Instance: `i-0835a5a35e0951816` (single instance behind ALB)
- RDS Database: `sfmwcdemov2-db`
- Salesforce Integration: OAuth 3LO via MCP Server

**Infrastructure Diagram:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Account: 611291728384                │
│                         Region: us-east-1                        │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    VPC (Virtual Private Cloud)              │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │              Public Subnet (us-east-1a)               │  │ │
│  │  │                                                        │  │ │
│  │  │  ┌──────────────────────────────────────────────┐    │  │ │
│  │  │  │  Application Load Balancer (ALB)             │    │  │ │
│  │  │  │  sfmwcdemov2-alb                             │    │  │ │
│  │  │  │  DNS: sfmwcdemov2-alb-1149431626...          │    │  │ │
│  │  │  │                                               │    │  │ │
│  │  │  │  Listeners: HTTP:80                           │    │  │ │
│  │  │  └───────────────────┬──────────────────────────┘    │  │ │
│  │  │                      │                                │  │ │
│  │  │                      │ Routes traffic to              │  │ │
│  │  │                      ▼                                │  │ │
│  │  │  ┌──────────────────────────────────────────────┐    │  │ │
│  │  │  │  Target Group: sfmwcdemov2-tg                │    │  │ │
│  │  │  │  Health Check: HTTP:80/                      │    │  │ │
│  │  │  │  Interval: 30s, Timeout: 5s                  │    │  │ │
│  │  │  └───────────────────┬──────────────────────────┘    │  │ │
│  │  │                      │                                │  │ │
│  │  │                      │ Contains                       │  │ │
│  │  │                      ▼                                │  │ │
│  │  │  ┌──────────────────────────────────────────────┐    │  │ │
│  │  │  │  Auto Scaling Group: sfmwcdemov2-asg         │    │  │ │
│  │  │  │  MinSize: 1, MaxSize: 3, Desired: 1          │    │  │ │
│  │  │  │                                               │    │  │ │
│  │  │  │  ┌────────────────────────────────────────┐  │    │  │ │
│  │  │  │  │  EC2 Instance                          │  │    │  │ │
│  │  │  │  │  i-0835a5a35e0951816                   │  │    │  │ │
│  │  │  │  │  Type: t3.micro                        │  │    │  │ │
│  │  │  │  │  State: running                        │  │    │  │ │
│  │  │  │  │  ⚠️  SINGLE POINT OF FAILURE           │  │    │  │ │
│  │  │  │  └────────────────────────────────────────┘  │    │  │ │
│  │  │  └──────────────────────────────────────────────┘    │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  │  ┌──────────────────────────────────────────────────────┐│ │
│  │  │              Private Subnet (us-east-1b)              ││ │
│  │  │                                                        ││ │
│  │  │  ┌──────────────────────────────────────────────┐    ││ │
│  │  │  │  RDS MySQL Database                          │    ││ │
│  │  │  │  sfmwcdemov2-db                              │    ││ │
│  │  │  │  Endpoint: sfmwcdemov2-db.crglxlsjmgc6...    │    ││ │
│  │  │  │                                               │    ││ │
│  │  │  │  Engine: MySQL 8.0.43                        │    ││ │
│  │  │  │  Instance: db.t3.micro                       │    ││ │
│  │  │  │  Multi-AZ: No (Single-AZ)                    │    ││ │
│  │  │  └──────────────────▲───────────────────────────┘    ││ │
│  │  │                     │                                 ││ │
│  │  │                     │ Database connections            ││ │
│  │  │                     │ from EC2 instance               ││ │
│  │  └─────────────────────┼─────────────────────────────────┘│ │
│  │                        │                                   │ │
│  └────────────────────────┼───────────────────────────────────┘ │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            │
                    ┌───────┴────────┐
                    │   Internet     │
                    │   Traffic      │
                    │   (HTTP)       │
                    └────────────────┘

Security Groups:
├─ ALB Security Group: Allows inbound HTTP (80) from 0.0.0.0/0
├─ EC2 Security Group: Allows inbound from ALB security group
└─ RDS Security Group: Allows inbound MySQL (3306) from EC2 security group

CloudWatch Metrics Monitored:
├─ ALB: RequestCount, HTTPCode_Target_5XX_Count, TargetResponseTime
├─ EC2: CPUUtilization, StatusCheckFailed
└─ RDS: DatabaseConnections, CPUUtilization, FreeableMemory

CloudTrail Events Tracked:
├─ EC2: StopInstances, StartInstances, RebootInstances
├─ RDS: RebootDBInstance, ModifyDBInstance
└─ AutoScaling: UpdateAutoScalingGroup, TerminateInstanceInAutoScalingGroup
```

**Key Architectural Issue:**
The Auto Scaling Group is configured with MinSize=1, creating a single point of failure. 
When the sole EC2 instance is stopped or fails, the ALB has zero healthy targets, 
causing complete service unavailability.

**DevOps Agent:**
- Webhook URL: `https://event-ai.us-east-1.api.aws/webhook/generic/6a14950d-4556-4b7e-adf5-802fcbdfc614`
- Agent Space ID: Stored in `.agent_space_id`
- Capabilities: AWS infrastructure analysis, Salesforce integration

**Required Steering Knowledge Base Entry:**

The DevOps Agent requires the following steering knowledge to properly investigate and update Salesforce cases:

```
You are a DevOps Agent. You help customers troubleshoot issues that are reported via Salesforce.

- You have a MCP Server that allows you to read Salesforce cases.
- The MCP Server has a tool that allows you to update Salesforce cases
- The update_sobject_record tool can be used to update a Salesforce record
- To update the case, create a FeedItem record

When investigating, look first for in CloudWatch and CloudTrail for maintenance events 
that could have caused the downtime.

Before you write the final investigation summary, you MUST ALWAYS first update the 
Salesforce case with details of your investigation. Double check that the case is 
updated first, before you write the final investigation.
```

This steering entry should be added to the Agent Space configuration via the AWS Console UI under the "Steering" or "Knowledge Base" section.

## Demo Workflow

### Step 1: Generate Baseline Traffic

Start the traffic generator to create baseline metrics:

```bash
./generate_alb_traffic.sh
```

**What it does:**
- Sends HTTP requests to the ALB at 2 requests/second
- Runs for 5 minutes by default (300 seconds)
- Shows real-time success/failure counts
- Creates CloudWatch metrics: RequestCount, TargetResponseTime, HTTPCode_Target_2XX_Count

**Optional parameters:**
```bash
# Custom duration and rate
./generate_alb_traffic.sh "" 600 5  # 10 minutes at 5 req/sec
```

**Expected output:**
```
==========================================
ALB Traffic Generator
==========================================
ALB DNS: sfmwcdemov2-alb-1149431626.us-east-1.elb.amazonaws.com
Duration: 300 seconds
Rate: 2 requests/second
==========================================

Testing ALB connection...
✓ ALB connection successful (HTTP 200)

Starting traffic generation...
Press Ctrl+C to stop

12:17:47 - Requests: 10 | Success: 10 | Failed: 0 | Success Rate: 100.0% | Time remaining: 595s
```

### Step 2: Simulate an Outage

While the traffic generator is running (after 1-2 minutes to establish baseline):

1. Open AWS Console
2. Navigate to EC2 > Instances
3. Select instance `i-0835a5a35e0951816`
4. Click **Instance State** > **Stop instance**
5. Wait ~30 seconds
6. Click **Instance State** > **Start instance**

**What happens:**
- ALB health checks fail
- Traffic generator shows increased failures
- Success rate drops from 100% to ~85-90%
- CloudWatch captures the incident metrics

**Expected traffic generator output during outage:**
```
12:19:00 - Requests: 160 | Success: 160 | Failed: 0 | Success Rate: 100.0% | Time remaining: 523s
12:19:16 - Requests: 190 | Success: 188 | Failed: 2 | Success Rate: 98.9% | Time remaining: 507s
12:19:20 - Requests: 200 | Success: 188 | Failed: 12 | Success Rate: 94.0% | Time remaining: 502s
12:19:34 - Requests: 210 | Success: 193 | Failed: 17 | Success Rate: 91.9% | Time remaining: 488s
12:20:31 - Requests: 260 | Success: 221 | Failed: 39 | Success Rate: 85.0% | Time remaining: 431s
12:20:36 - Requests: 270 | Success: 231 | Failed: 39 | Success Rate: 85.5% | Time remaining: 426s
```

### Step 3: Wait for Metrics

After the traffic generator completes:

1. **Wait 2-3 minutes** for CloudWatch metrics to fully populate
2. Note the incident time (e.g., 12:19 PM local / 20:19 UTC)
3. Note the total failed requests (e.g., 39 failures)

### Step 4: Create or Update Salesforce Case

If you don't have an existing case, create one in Salesforce:

**Example Case Details:**

```
Subject: Load Balancer unavailable

Description: 
My Load Balancer was down this morning. The ALB was unavailable for approximately 
10 minutes between 12:15pm and 12:30pm (Pacific Standard Time) on February 3rd 2026.

Account: 611291728384
Region: us-east-1
Load Balancer: sfmwcdemov2-alb

Priority: High
Status: New
```

**Customize for your test:**
- Update the time to match when you stopped the EC2 instance
- Adjust the duration based on your actual outage window
- Keep the Account, Region, and Load Balancer details as shown

**Note the Case Number** (e.g., 00001124)

### Step 5a: Manually Start Investigation

Use the DevOps Agent console to manually initiate an investigation. 

Investigation detauls: 

Your PRIMARY TASK is to add a Feedback record to Salesforce case 00001143 with root cause findings. 

Starting Point:

To do this: First, investigate case 00001143 to determine the root cause. Second, create a FeedItem record for case 00001143 with your findings. The FeedItem must have Type='TextPost' and ParentId set to the Case Id. Use the Body field for your root cause analysis. Before you write the final investigation summary, you MUST ALWAYS update the Salesforce case with details of your investigation. Double check that the case is updated before you write the final investigation.

### Step 5b: Run Automated Investigation

Trigger the DevOps Agent to investigate and update the case:

```bash
./investigate_and_update_case.sh 00001124
```

Replace `00001124` with your actual case number.

> **Note:** We are working to improve this demo by automating this step. In the future, 
> the investigation will be triggered automatically via Salesforce Flows when a case 
> is created or updated, which will call the AWS webhook directly without requiring 
> manual script execution.

**What it does:**
1. Sends webhook to DevOps Agent with investigation request
2. Agent queries Salesforce for case details
3. Agent discovers AWS infrastructure topology
4. Agent analyzes CloudWatch metrics during incident window
5. Agent examines CloudTrail for infrastructure changes
6. Agent determines root cause
7. **Agent posts findings to Salesforce case as a FeedItem**

**Expected output:**
```
==========================================
Salesforce Case Investigation & Update
==========================================
Case Number: 00001124
Incident ID: SF-CASE-00001124-202602031839
Priority: HIGH
==========================================

Instructions being sent:
Your PRIMARY TASK is to add a comment to Salesforce case 00001124 with root cause findings...

==========================================

Sending investigation request...

✓ Investigation request sent successfully!
  HTTP Status: 200
  Response: {"message": "Webhook received"}

==========================================
Investigation started
==========================================
The DevOps Agent should now:
  1. Read and analyze case 00001124
  2. Determine the root cause
  3. Add a comment to the case with findings

Check your DevOps Agent console for results.
==========================================
```

### Step 6: Review Results

**In DevOps Agent Console:**

Navigate to: `https://[your-agent-space].aidevops.global.app.aws/dashboard`

You'll see the investigation with:
- Topology discovery
- CloudWatch metrics analysis
- CloudTrail event analysis
- Root cause determination
- Salesforce FeedItem creation

**In Salesforce:**

1. Open the case in Salesforce Lightning
2. Navigate to the **Activity** or **Feed** tab
3. You'll see a new post from "Joe McMaster" (the DevOps Agent)

**Example finding:**
```
ROOT CAUSE ANALYSIS - Case 00001127

=== INCIDENT SUMMARY ===
Application Load Balancer 'sfmwcdemov2-alb' was unavailable for approximately 
10 minutes between 20:15-20:30 UTC (12:15-12:30pm PST) on February 3rd, 2026.

=== ROOT CAUSE ===
Manual stop/start of EC2 instance i-0835a5a35e0951816 by user 'manconor-Isengard' 
caused complete ALB unavailability.

=== DETAILED FINDINGS ===
1. CloudTrail Evidence:
   - 20:10:36 UTC: Instance i-0835a5a35e0951816 rebooted (1st time)
   - 20:19:14 UTC: Instance i-0835a5a35e0951816 rebooted (2nd time)
   - 20:19:43 UTC: Instance STOPPED by manconor-Isengard via AWS Console
   - 20:20:18 UTC: Instance STARTED (35 seconds downtime)
   - Source IP: 98.37.173.153
   - User Agent: Chrome browser on macOS

2. ALB Impact Metrics:
   - RequestCount dropped to 0 from 20:10-20:16 UTC and 20:27-20:31 UTC
   - HTTPCode_ELB_5XX_Count spiked to 30 errors at 20:19 UTC
   - Total unavailability period: ~11 minutes

3. Infrastructure Context:
   - Instance i-0835a5a35e0951816 was the ONLY instance in Auto Scaling Group 
     'sfmwcdemov2-asg'
   - ASG configuration: MinSize=1, DesiredCapacity=1, MaxSize=3
   - When stopped, the ALB had zero available targets to route traffic

=== WHY THIS CAUSED THE OUTAGE ===
The manual stop operation removed the only healthy backend target from the ALB's 
target group. With no instances available to serve traffic, the ALB could not 
process any requests, resulting in complete service unavailability. The two 
reboots prior to the stop/start suggest troubleshooting activities that 
escalated to a more disruptive intervention.

=== RECOMMENDATIONS ===
1. IMMEDIATE: Increase ASG MinSize to at least 2 instances for high availability
2. Implement change management procedures requiring approval before stopping 
   production instances
3. Enable ASG CloudWatch detailed metrics for better observability
4. Consider connection draining configuration to minimize impact during maintenance
5. Review IAM policies to restrict instance stop/start actions in production

Investigation completed at 2026-02-03T20:27 UTC by AWS DevOps Agent.
```

### Step 7: Generate Mitigation Plan (Optional)

After the investigation completes, you can ask the DevOps Agent to generate a mitigation plan to prevent future occurrences.

**In the DevOps Agent Console:**

1. Navigate to the completed investigation
2. Click on the chat interface
3. Ask: "Please create a mitigation plan to prevent this issue from happening again"

**Example Mitigation Plan Generated:**

```
MITIGATION PLAN

Title: Increase Auto Scaling Group 'sfmwcdemov2-asg' minimum capacity from 1 to 2 
instances to eliminate single point of failure

Rationale:
The root cause analysis identified that Application Load Balancer 'sfmwcdemov2-alb' 
(arn:aws:elasticloadbalancing:us-east-1:611291728384:loadbalancer/app/sfmwcdemov2-alb/e94213e1d5c5fa17) 
became completely unavailable for approximately 10 minutes when user manconor-Isengard 
manually stopped the only EC2 instance (i-0835a5a35e0951816) in Auto Scaling Group 
'sfmwcdemov2-asg' at 20:19:43 UTC on February 3, 2026. 

The ASG was configured with MinSize=1, MaxSize=3, and DesiredCapacity=1, creating a 
single point of failure. When the sole instance was stopped during troubleshooting 
activities, the ALB had zero healthy targets available, causing complete service 
disruption with RequestCount dropping to 0 and HTTPCode_ELB_5XX_Count spiking to 
30 errors. 

This mitigation addresses a capacity limit issue by increasing the minimum instance 
count to 2, ensuring that at least one healthy instance remains available to serve 
traffic during manual operations, instance failures, or maintenance activities.

Affected Resources:
- AWS Account: 611291728384
- Region: us-east-1
- Auto Scaling Group: sfmwcdemov2-asg
- Load Balancer: sfmwcdemov2-alb

Implementation Steps:
1. Update ASG minimum capacity:
   aws autoscaling update-auto-scaling-group \
     --auto-scaling-group-name sfmwcdemov2-asg \
     --min-size 2 \
     --desired-capacity 2 \
     --region us-east-1

2. Verify new instances launch:
   aws autoscaling describe-auto-scaling-groups \
     --auto-scaling-group-names sfmwcdemov2-asg \
     --region us-east-1 \
     --query 'AutoScalingGroups[0].[MinSize,DesiredCapacity,Instances[].InstanceId]'

3. Confirm ALB has 2 healthy targets:
   aws elbv2 describe-target-health \
     --target-group-arn <target-group-arn> \
     --region us-east-1

Expected Outcome:
- Minimum 2 instances always running
- ALB maintains at least 1 healthy target during maintenance
- Zero-downtime for single instance failures or manual operations
- Estimated additional cost: ~$30-50/month for second t3.micro instance

Validation:
Test by stopping one instance - ALB should continue serving traffic with remaining instance.
```

The DevOps Agent can generate these mitigation plans automatically and even create implementation tasks or runbooks.

## Key Features Demonstrated

### 1. Automated Investigation
- No manual log analysis required
- Agent autonomously discovers topology
- Correlates metrics across multiple AWS services
- Identifies root cause from CloudTrail events

### 2. Salesforce Integration
- Automatic case updates via FeedItem (visible in Lightning)
- Structured root cause analysis
- Actionable recommendations
- Audit trail of investigation

### 3. Structured Metadata
The script uses metadata to guide the Agent:
```json
{
  "primary_goal": "create_salesforce_feeditem",
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
    }
  }
}
```

### 4. Real-World Metrics
- CloudWatch metrics show actual traffic patterns
- Failure rates correlate with infrastructure events
- Timeline reconstruction from multiple data sources

## Troubleshooting

### Traffic Generator Issues

**Problem:** Connection timeout
```bash
✗ Failed to connect to ALB
```

**Solution:** Check ALB DNS name and security groups:
```bash
aws elbv2 describe-load-balancers --region us-east-1 \
  --query 'LoadBalancers[?contains(LoadBalancerName, `sfmwcdemov2`)].DNSName' \
  --output text
```

### Investigation Issues

**Problem:** Comment not visible in Salesforce

**Solution:** The script uses FeedItem (not CaseComment) for Lightning visibility. Check the Activity/Feed tab, not the Comments section.

**Problem:** Investigation completes but no Salesforce update

**Solution:** Check DevOps Agent console for errors. The Agent must have:
- Valid Salesforce OAuth token
- Permission to create FeedItem records
- Correct Case Id from query

### Webhook Issues

**Problem:** "Webhook received" but no investigation starts

**Solution:** Check Agent Space configuration:
```bash
aws cloudsmithcontrolplane get-agent-space \
  --agent-space-id $(cat .agent_space_id) \
  --endpoint-url "https://api.prod.cp.aidevops.us-east-1.api.aws" \
  --region us-east-1
```

## Advanced Usage

### Custom Incident Scenarios

**Test different incident types:**

1. **RDS Database Reboot:**
   ```bash
   aws rds reboot-db-instance \
     --db-instance-identifier sfmwcdemov2-db \
     --region us-east-1
   ```

2. **Security Group Changes:**
   ```bash
   # Remove a rule to break connectivity
   aws ec2 revoke-security-group-ingress \
     --group-id sg-xxx \
     --protocol tcp \
     --port 80 \
     --cidr 0.0.0.0/0 \
     --region us-east-1
   ```

3. **Auto Scaling Events:**
   - Trigger scale-in/scale-out
   - Observe instance termination/launch

### Custom Traffic Patterns

**High load test:**
```bash
./generate_alb_traffic.sh "" 600 10  # 10 req/sec for 10 minutes
```

**Extended baseline:**
```bash
./generate_alb_traffic.sh "" 1800 2  # 30 minutes at 2 req/sec
```

### Multiple Investigations

The incident ID format allows multiple investigations of the same case:
```
SF-CASE-00001124-202602031839  # First investigation
SF-CASE-00001124-202602031945  # Second investigation
```

Each investigation creates a separate FeedItem in Salesforce.

## Files Reference

| File | Purpose |
|------|---------|
| `investigate_and_update_case.sh` | Main investigation script |
| `generate_alb_traffic.sh` | Traffic generator for ALB |
| `check_case_and_comment.sh` | Verify case/comment details |
| `query_case_comments.sh` | Query all comments on a case |
| `publish_comment.sh` | Publish unpublished comments |
| `.agent_space_id` | Stores Agent Space ID |

## Best Practices

1. **Always establish baseline** - Run traffic for 1-2 minutes before simulating outage
2. **Wait for metrics** - Allow 2-3 minutes after incident for CloudWatch to populate
3. **Document incident time** - Note exact time for correlation with metrics
4. **Review Agent console** - Check investigation steps and API calls
5. **Verify Salesforce update** - Confirm FeedItem appears in Activity feed

## Next Steps

- Integrate with incident management workflows
- Create custom steering rules for specific incident types
- Add automated alerting triggers
- Extend to other AWS services (Lambda, DynamoDB, etc.)
- Implement multi-region investigations

## Support

For issues or questions:
1. Check DevOps Agent console for detailed logs
2. Review CloudWatch metrics for data availability
3. Verify Salesforce MCP Server OAuth status
4. Check AWS CloudTrail for API call history

## References

- [AWS DevOps Agent Documentation](https://docs.aws.amazon.com/devopsagent/latest/userguide/)
- [Salesforce MCP Server](https://api.salesforce.com/platform/mcp/)
- [CloudWatch Metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/)
- [Application Load Balancer Metrics](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
