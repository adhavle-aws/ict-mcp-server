#!/bin/bash

# Script to patch AWS CLI with CloudSmith (AWS DevOps Agent) service models
# This must be run before using create_devops_agent_space.sh

set -e

echo "=========================================="
echo "CloudSmith AWS CLI Setup"
echo "=========================================="
echo "This script will patch your AWS CLI with CloudSmith service models"
echo ""

# Check if JSON files already exist
if [ ! -f "cloudsmithcontrolplane-2018-05-10.normal.json" ] || [ ! -f "cloudsmithdataplane-2025-07-17.normal.json" ]; then
    echo "ERROR: Service model JSON files not found!"
    echo ""
    echo "You need to manually download the following files:"
    echo ""
    echo "1. Control Plane Model:"
    echo "   Navigate to: https://code.amazon.com/packages/CloudSmithControlPlaneServiceModel/releases"
    echo "   Download: smithyprojections/CloudSmithControlPlaneServiceModel/aws-sdk-external/c2j/cloudsmithcontrolplane-2018-05-10.normal.json"
    echo "   Save as: cloudsmithcontrolplane-2018-05-10.normal.json"
    echo ""
    echo "2. Data Plane Model:"
    echo "   Navigate to: https://code.amazon.com/packages/CloudSmithDataPlaneServiceModel/releases"
    echo "   Download: smithyprojections/CloudSmithDataPlaneServiceModel/aws-sdk-external/c2j/cloudsmithdataplane-2025-07-17.normal.json"
    echo "   Save as: cloudsmithdataplane-2025-07-17.normal.json"
    echo ""
    echo "Place both files in the current directory and run this script again."
    exit 1
fi

echo "✓ Found service model files"
echo ""
echo "Patching AWS CLI..."

# Add the control plane model
echo "Adding cloudsmithcontrolplane command..."
aws configure add-model \
    --service-model "file://${PWD}/cloudsmithcontrolplane-2018-05-10.normal.json" \
    --service-name cloudsmithcontrolplane

# Add the data plane model
echo "Adding cloudsmithdataplane command..."
aws configure add-model \
    --service-model "file://${PWD}/cloudsmithdataplane-2025-07-17.normal.json" \
    --service-name cloudsmithdataplane

echo ""
echo "=========================================="
echo "✓ AWS CLI patched successfully!"
echo "=========================================="
echo ""
echo "Note: The commands may show errors in help but should work for actual operations."
echo "You can now run: ./create_devops_agent_space.sh <agent-space-name>"
echo ""
