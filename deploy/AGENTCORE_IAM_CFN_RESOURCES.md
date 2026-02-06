# AgentCore role: Permissions for CloudFormation-created resources

When CloudFormation creates or deletes stack resources, it uses the **caller’s** credentials (the AgentCore execution role). That role therefore needs permissions for every resource type in your templates.

This repo attaches three **inline** policies (in addition to the Bedrock runtime policy) so typical AI-generated stacks can be created and deleted:

| Policy name | Purpose |
|-------------|--------|
| **AgentCoreSSMParameters** | `ssm:GetParameters` for AMI and other SSM parameters in templates. See [AGENTCORE_IAM_SSM.md](AGENTCORE_IAM_SSM.md). |
| **AgentCoreCloudWatchLogs** | CloudWatch Dashboards and CloudWatch Logs (create/delete). See [AGENTCORE_IAM_CLOUDWATCH_LOGS.md](AGENTCORE_IAM_CLOUDWATCH_LOGS.md). |
| **AgentCoreCFnResources** | S3, Lambda, Kinesis, Glue, Athena, Step Functions, and IAM (roles/policies) so stacks can create and delete these resources. |

## Attach the CFn resources policy

If stack create/delete fails with `AccessDenied` on S3, Lambda, Kinesis, Glue, Athena, Step Functions, or IAM, attach (or fix) the resources policy:

```bash
cd deploy
aws iam put-role-policy \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a \
  --policy-name AgentCoreCFnResources \
  --policy-document file://agentcore-cfn-resources-policy.json
```

Use your actual AgentCore role name if different.

## What’s in AgentCoreCFnResources

- **S3**: Create/delete buckets, get/put/delete objects, lifecycle, versioning, encryption.
- **Lambda**: Create/delete/update functions, permissions, versions.
- **Kinesis**: Create/delete/describe streams, tags.
- **Glue**: Databases, tables, crawlers, jobs, connections, partitions.
- **Athena**: Work groups, data catalogs.
- **Step Functions**: Create/delete/update state machines, tags.
- **IAM**: Create/delete roles, PassRole, attach/detach and inline role policies (so templates can create execution roles for Lambda, Step Functions, etc.).

If you add new resource types in templates (e.g. API Gateway, DynamoDB, EMR), add the corresponding actions to this policy or a new inline policy on the same role.
