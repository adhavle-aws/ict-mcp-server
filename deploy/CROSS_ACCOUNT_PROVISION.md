# Cross-Account Provisioning

The MCP server runs in **611291728384** (AgentCore / aws-gaurav) but can create CloudFormation stacks (and resolve VPC/subnets) in another account, e.g. **471112858498**.

## How it works

When `CFN_TARGET_ACCOUNT_ID` and `CFN_TARGET_ROLE_NAME` (or `CFN_TARGET_ROLE_ARN`) are set in the **runtime environment**, `get_cfn_client()` and `get_ec2_client()` assume that role in the target account before calling CloudFormation/EC2. So `provision_cfn_stack`, `delete_cfn_stack`, and `get_cfn_stack_events` all operate in the target account.

## Setup

### 1. Target account (471112858498)

Create an IAM role that the AgentCore runtime can assume, with permissions to create/manage stacks and describe VPCs/subnets.

**Role name (example):** `CrossAccountAccessRole` (or `AgentCoreProvisionRole`).

**Trust policy** (allow the runtime in 611291728384 to assume this role):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::611291728384:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Permissions:** Attach a policy that allows at least:

- `cloudformation:*`
- `ec2:DescribeVpcs`, `ec2:DescribeSubnets`, `ec2:DescribeSecurityGroups`
- Any other permissions needed for the resources your templates create (e.g. IAM, Lambda, S3, RDS, etc.). You can reuse the same permissions as in `agentcore-full-policy.json` but scoped to this account.

Example: create a role with the trust policy above and attach `deploy/agentcore-full-policy.json` (or a copy tailored for 471112858498).

### 2. Source account (611291728384)

Grant the AgentCore **runtime** role permission to assume the role in the target account.

Attach an inline policy to the runtime role allowing AssumeRole. Example policy is in `deploy/agentcore-assume-role-policy.json`. From the repo (with AWS profile for 611291728384):

```bash
aws iam put-role-policy \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a \
  --policy-name CrossAccountProvision \
  --policy-document file://deploy/agentcore-assume-role-policy.json
```

Or add the statement manually in the IAM console for  
`arn:aws:iam::611291728384:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a`.

### 3. Runtime environment (AgentCore)

Set environment variables for the MCP runtime so it uses the target account for provision:

**Option A – account + role name**

- `CFN_TARGET_ACCOUNT_ID=471112858498`
- `CFN_TARGET_ROLE_NAME=CrossAccountAccessRole`

**Option B – full role ARN**

- `CFN_TARGET_ROLE_ARN=arn:aws:iam::471112858498:role/CrossAccountAccessRole`

**Default VPC in target account:** Provision auto-fills VpcId/PublicSubnetIds/PrivateSubnetIds using the **target account’s** default VPC (EC2 is called with the assumed role). If the target account has no default VPC, set an optional fallback:

- `CFN_TARGET_DEFAULT_VPC_ID=vpc-xxxxxxxx` (a VPC in the target account that has subnets)

Where to set these depends on how you run AgentCore (e.g. Bedrock AgentCore environment configuration, or container env / Dockerfile for deploy).

## Verification

After setup, call `provision_cfn_stack` with a small template. The stack should appear in account **471112858498** in the chosen region (e.g. us-east-1), not in 611291728384.

## Clearing cross-account

Remove or unset `CFN_TARGET_ACCOUNT_ID`, `CFN_TARGET_ROLE_NAME`, and `CFN_TARGET_ROLE_ARN`. Provisioning will use the runtime account (611291728384) again.

---

## IAM user: assume role in 471112858498 and create resources (Console / CLI)

To let **your IAM user** (e.g. `adhavle`) assume a role in account **471112858498** and create resources there (Console Switch Role or CLI):

### 1. In target account (471112858498)

Create an IAM role (e.g. **adhavle** or **AdhavleConsoleRole**) that your user can assume.

**Trust policy** – allow your IAM user from your source account (replace `YOUR_ACCOUNT_ID` and `YOUR_IAM_USERNAME`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:user/YOUR_IAM_USERNAME"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Example: if your user is `adhavle` in account `611291728384`, use  
`"AWS": "arn:aws:iam::611291728384:user/adhavle"`.

**Permissions:** Attach a policy that allows creating and managing resources (e.g. **PowerUserAccess** or **AdministratorAccess**), or a custom policy with the services you need (CloudFormation, EC2, S3, RDS, Lambda, IAM, etc.).

### 2. In your account (where your IAM user lives)

Grant your IAM user permission to assume the role in 471112858498.

**Inline policy** (attach to your IAM user, e.g. `adhavle`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::471112858498:role/adhavle"
    }
  ]
}
```

Use the **role name** you created in step 1 (e.g. `adhavle` or `AdhavleConsoleRole`).

### 3. Use it

- **Console:** Account menu (top right) → **Switch Role** → Account `471112858498`, Role name `adhavle` (or whatever you created) → Switch Role. You can then create and manage resources in 471112858498.
- **CLI:**  
  `aws sts assume-role --role-arn arn:aws:iam::471112858498:role/adhavle --role-session-name my-session`  
  then use the returned credentials, or configure a named profile that uses `role_arn` and `source_profile`.
