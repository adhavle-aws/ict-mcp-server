# AgentCore role: SSM permission for CloudFormation

If provisioning a stack fails with:

```text
User: arn:aws:sts::...:assumed-role/AmazonBedrockAgentCoreSDKRuntime-.../BedrockAgentCore-...
is not authorized to perform: ssm:GetParameters on resource: arn:aws:ssm:...::parameter/aws/service/...
```

then the **AgentCore runtime execution role** is missing permission for CloudFormation to resolve SSM parameters (e.g. latest AMI IDs) when creating the stack.

## Fix

Attach an IAM policy that allows `ssm:GetParameters` on AWS service parameters (e.g. AMI IDs). The policy below allows all `aws/service/*` parameters in any region so templates can resolve `ami-amazon-linux-latest`, `ami-amazon-linux-2`, etc.

### Option 1: AWS Console

1. IAM → Roles → **AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a**
2. Add permissions → Create inline policy (or attach the policy below as a custom policy).
3. Use the JSON under "Policy JSON" below.

### Option 2: AWS CLI

Create a file `agentcore-ssm-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameters"
      ],
      "Resource": [
        "arn:aws:ssm:*::parameter/aws/service/*"
      ]
    }
  ]
}
```

Then attach it to the role:

```bash
aws iam put-role-policy \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a \
  --policy-name AgentCoreSSMParameters \
  --policy-document file://agentcore-ssm-policy.json
```

Use your AgentCore execution role name and region if different.

### Policy JSON (for console)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameters"
      ],
      "Resource": [
        "arn:aws:ssm:*::parameter/aws/service/*"
      ]
    }
  ]
}
```

After adding this permission, retry **Provision** in the Deployment Agent tab.
