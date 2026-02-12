#!/usr/bin/env bash
# Deploy AWS Architect AI Visualforce page to the storm org.
# Prereq: sf org login web --alias storm --instance-url https://storm-1337260a3c1ead.my.salesforce.com
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "Deploying to org: storm-org (storm-1337260a3c1ead.my.salesforce.com)"
sf project deploy start --source-dir . --target-org storm-org
echo "Done. Open: https://storm-1337260a3c1ead.my.salesforce.com/apex/AWSArchitectAI"
