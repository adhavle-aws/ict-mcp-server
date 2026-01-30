#!/bin/bash
# Package FastAPI backend for Lambda

set -e

echo "📦 Packaging FastAPI backend for Lambda..."

# Clean up
rm -rf package lambda.zip

# Create package directory
mkdir -p package

# Install dependencies
uv pip install -r requirements.txt --target package/ --python-platform linux --python-version 3.11

# Copy code
cp handler.py package/
cp streamable_http_sigv4.py package/

# Create zip
cd package
zip -r ../lambda.zip . -q
cd ..

echo "✅ Lambda package created: lambda.zip"
echo "   Size: $(du -h lambda.zip | cut -f1)"
