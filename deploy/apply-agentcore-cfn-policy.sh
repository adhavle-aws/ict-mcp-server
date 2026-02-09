#!/usr/bin/env bash
# Apply AgentCore runtime role policy. Default: agentcore-full-policy.json (comprehensive).
# Usage: ./apply-agentcore-cfn-policy.sh [agentcore-full-policy.json|agentcore-cfn-resources-policy.json]
# Run from repo root or deploy/. Uses AWS_PROFILE or default profile.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLE_NAME="AmazonBedrockAgentCoreSDKRuntime-us-east-1-b4d325b89a"
POLICY_NAME="AgentCoreCFnResources"
POLICY_FILE="${1:-${SCRIPT_DIR}/agentcore-full-policy.json}"

echo "Applying $(basename "$POLICY_FILE") to role $ROLE_NAME"
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "file://${POLICY_FILE}"

echo "Done. Role $ROLE_NAME now has inline policy $POLICY_NAME."
