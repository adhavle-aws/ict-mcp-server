# Learnings from aws-iac-mcp-server Compliance Checker

The [aws-iac-mcp-server](https://github.com/awslabs/mcp/tree/main/src/aws-iac-mcp-server) includes a **CloudFormation compliance checker** ([cloudformation_compliance_checker.py](https://github.com/awslabs/mcp/blob/main/src/aws-iac-mcp-server/awslabs/aws_iac_mcp_server/tools/cloudformation_compliance_checker.py)) that validates templates against **AWS CloudFormation Guard** rules and returns violations with remediation hints. Here’s what we can reuse.

## What the compliance checker does

1. **Guard rules** – Uses [CloudFormation Guard](https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html) (via `guardpycfn`) to evaluate a template against policy-as-code rules (e.g. S3 encryption, public access block, RDS not public).
2. **Structured output** – Returns:
   - `compliance_results`: `overall_status` (COMPLIANT / VIOLATIONS_FOUND), `total_violations`, `rule_sets_applied`
   - `violations`: list of `{ rule_id, severity, resource, resource_type, message, remediation }`
   - `message`: summary for the user
3. **Remediation from rules** – Parses `Fix: ...` comments from the `.guard` rules file and attaches them to each violation so the LLM or user knows how to fix it.
4. **Default rules** – Ships with `default_guard_rules.guard` (S3, EC2, RDS, IAM, etc.) in the package `data/` directory.

## What we already do vs compliance

| Concern | Our server | Compliance checker |
|--------|------------|---------------------|
| Template **syntax** / schema | ✅ `validate_cfn_template` (CloudFormation `validate_template` API) | ❌ Guard does not validate syntax |
| **Security / policy** (e.g. S3 encrypted, no public RDS) | ❌ Not checked | ✅ Guard rules |
| Auto-fix | ✅ Claude + schema in `validate_cfn_template` | ❌ No auto-fix; remediation text only |
| Response shape | ✅ success, valid, error, template | ✅ compliance_results, violations, remediation |

So: **we cover “valid template”; they cover “template matches policy.”** Both are useful; they’re complementary.

## How to get compliance checking

### Option A: Use aws-iac-mcp-server for compliance

- Run the [aws-iac-mcp-server](https://github.com/awslabs/mcp/tree/main/src/aws-iac-mcp-server) (e.g. `cloudformation_pre_deploy_validation` or their compliance tool) in addition to our server.
- They use `guardpycfn>=0.1.0` and ship a full `default_guard_rules.guard`. No extra work in our codebase.

### Option B: Add an optional compliance step in our server

- **Dependency:** `guardpycfn` (as in aws-iac-mcp-server) or the public [cfn-guard-rs](https://pypi.org/project/cfn-guard-rs/) (`run_checks(rules_str, data_dict)`).
- **Rules:** Bundle a small `.guard` file (e.g. S3 encryption + public access block + RDS not public) or load from a path.
- **Tool:** e.g. `check_cfn_compliance(template_body, rules_file_path=None)` that returns the same shape: `compliance_results`, `violations` (with `remediation`), `message`.
- **When to run:** After `validate_cfn_template` passes and before `provision_cfn_stack`, so users see both “valid” and “compliant.”

### Option C: Align our validate response shape

- When `validate_cfn_template` fails, we already return `success`, `valid`, `error`, and optionally `template` (fixed). We can also return a **violations** list (e.g. one item: `rule_id: "TemplateValidation", message: <error>, remediation: "Run with auto_fix=true or fix the reported property."`) so agents/UI can treat “syntax errors” and “policy violations” the same way (one list of violations with remediation).

## Takeaways

1. **Guard = policy, not syntax** – Use CloudFormation `validate_template` for validity; use Guard for security/best-practice rules.
2. **Violations + remediation** – Returning `violations[]` with `message` and `remediation` is a good pattern for both syntax and policy failures.
3. **Fix comments in rules** – If we add Guard, put `Fix: ...` in the rule so we can expose remediation without calling an LLM.
4. **Rules location** – Either bundle a minimal `.guard` in the repo or point to the aws-iac-mcp-server default rules (e.g. copy a subset) so we don’t depend on their package.

Our server already returns a **violations**-style entry when validation fails (see `validate_cfn_template`). For full policy compliance, add `guardpycfn` + a rules file (Option B) or use aws-iac-mcp-server (Option A).
