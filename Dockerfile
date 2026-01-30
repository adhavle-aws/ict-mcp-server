# Dockerfile for CloudFormation MCP Server with Diagram Support
# Based on AgentCore Python runtime with GraphViz

FROM public.ecr.aws/amazonlinux/amazonlinux:2023

# Install system dependencies
RUN yum update -y && \
    yum install -y \
        python3.13 \
        python3.13-pip \
        graphviz \
        graphviz-devel \
        gcc \
        python3.13-devel && \
    yum clean all && \
    rm -rf /var/cache/yum

# Set Python 3.13 as default
RUN ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/pip3.13 /usr/bin/pip3

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY mcp_server.py .
COPY streamable_http_sigv4.py .
COPY __init__.py .

# Expose port for MCP server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run MCP server
CMD ["python3", "mcp_server.py"]
