# AgentCore role: CloudWatch and CloudWatch Logs for CloudFormation

**Policy name:** `AgentCoreCloudWatchLogs` (inline). For other required permissions (SSM, S3, Lambda, Kinesis, etc.) see [AGENTCORE_IAM_SSM.md](AGENTCORE_IAM_SSM.md) and [AGENTCORE_IAM_CFN_RESOURCES.md](AGENTCORE_IAM_CFN_RESOURCES.md).

If stack **creation** or **rollback/delete** fails with:

- `User: ... is not authorized to perform: cloudwatch:DeleteDashboards on resource: ... because no identity-based policy allows the cloudwatch:DeleteDashboards action`
- `User: ... is not authorized to perform: logs:DeleteLogGroup on resource: ... because no identity-based policy allows the logs:DeleteLogGroup action`

then the **AgentCore runtime execution role** is missing permissions for CloudFormation to create and delete CloudWatch dashboards and CloudWatch Logs log groups.

## Fix

Attach an IAM policy that allows CloudWatch Dashboard and CloudWatch Logs actions used by CloudFormation.

### Option 1: AWS Console

1. IAM → Roles → **AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a**
2. Add permissions → Create inline policy.
3. Choose JSON and paste the contents of `agentcore-cloudwatch-logs-policy.json` (or the JSON below).
4. Name the policy **AgentCoreCloudWatchLogs** and save.

### Option 2: AWS CLI

From the `deploy` directory (or adjust path to the JSON file):

```bash
aws iam put-role-policy \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a \
  --policy-name AgentCoreCloudWatchLogs \
  --policy-document file://agentcore-cloudwatch-logs-policy.json
```

Use your AgentCore execution role name if different.

### Policy JSON (for console)

Use the contents of `deploy/agentcore-cloudwatch-logs-policy.json`, or:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchDashboard",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutDashboard",
        "cloudwatch:GetDashboard",
        "cloudwatch:DeleteDashboards",
        "cloudwatch:ListDashboards"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:PutRetentionPolicy",
        "logs:DeleteRetentionPolicy",
        "logs:TagLogGroup",
        "logs:UntagLogGroup",
        "logs:PutLogEvents",
        "logs:PutResourcePolicy",
        "logs:DeleteResourcePolicy"
      ],
      "Resource": "*"
    }
  ]
}
```

After adding this policy, **future** stacks can create/delete dashboards and log groups. For a stack already in `ROLLBACK_FAILED`, see below.

---

## If the stack is already in ROLLBACK_FAILED

After you add the policy:

1. **Option A – Retry rollback (recommended)**  
   In the AWS Console: CloudFormation → select the stack → **Stack actions** → **Continue update rollback**. CloudFormation will retry deleting the failed resources; with the new permissions it should succeed.

2. **Option B – Delete stack and leave resources**  
   If rollback still fails (e.g. other issues), you can delete the stack and choose to **retain** the resources that failed to delete. Then delete the dashboard and log group manually if desired:
   - CloudWatch → Dashboards → delete the dashboard named like `...-monitoring`
   - CloudWatch Logs → Log groups → delete `/aws/vendedlogs/states/...-orchestration`

3. **Option C – Delete resources manually, then delete stack**  
   Delete the CloudWatch dashboard and the Step Functions log group manually (same as in B), then run **Continue update rollback** or **Delete stack** again.
