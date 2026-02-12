#!/usr/bin/env bash
# Lint CloudFormation canned templates with cfn-lint.
# Install cfn-lint first: pip install -r requirements-lint.txt
# See: https://github.com/aws-cloudformation/cfn-lint
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
CFN_LINT=""
if command -v cfn-lint &>/dev/null; then
  CFN_LINT="cfn-lint"
elif python3 -c "import cfn_lint" 2>/dev/null; then
  CFN_LINT="python3 -m cfn_lint"
fi
if [ -z "$CFN_LINT" ]; then
  echo "cfn-lint not found. Install with: pip install -r requirements-lint.txt"
  exit 1
fi
echo "Linting templates in templates/"
# W3691: RDS engine version deprecation is a moving target; we use a supported major version
$CFN_LINT templates/*.yaml -r us-east-1 --ignore-checks W3691
echo "Done. No issues found."
