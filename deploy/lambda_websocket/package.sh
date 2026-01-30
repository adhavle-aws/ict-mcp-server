#!/bin/bash
set -e

echo "📦 Packaging WebSocket Lambda..."

rm -rf package lambda.zip
mkdir -p package

# Install dependencies
uv pip install -r requirements.txt --target package/ --python-platform linux --python-version 3.11

# Copy handler
cp handler.py package/

# Create zip
cd package
zip -r ../lambda.zip . -q
cd ..

echo "✅ Lambda package created: lambda.zip"
echo "   Size: $(du -h lambda.zip | cut -f1)"
