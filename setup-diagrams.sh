#!/bin/bash

# Setup script for AWS Diagram generation
# Installs GraphViz and Python dependencies

echo "🔧 Setting up AWS Diagram generation..."

# Detect OS and install GraphViz
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "📦 Installing GraphViz on macOS..."
    if command -v brew &> /dev/null; then
        brew install graphviz
    else
        echo "❌ Homebrew not found. Please install from: https://brew.sh/"
        exit 1
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    echo "📦 Installing GraphViz on Linux..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y graphviz graphviz-dev
    elif command -v yum &> /dev/null; then
        sudo yum install -y graphviz graphviz-devel
    else
        echo "❌ Package manager not found. Please install GraphViz manually."
        exit 1
    fi
else
    echo "❌ Unsupported OS: $OSTYPE"
    echo "Please install GraphViz manually: https://www.graphviz.org/download/"
    exit 1
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "✅ Setup complete!"
echo ""
echo "You can now run the MCP server with:"
echo "  python mcp_server.py"
