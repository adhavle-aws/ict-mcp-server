/**
 * Backend proxy for CloudFormation MCP Server
 * Handles AWS SigV4 signing for AgentCore Runtime requests
 */
const express = require('express');
const cors = require('cors');
const { SignatureV4 } = require('@smithy/signature-v4');
const { Sha256 } = require('@aws-crypto/sha256-js');
const { HttpRequest } = require('@smithy/protocol-http');
const { defaultProvider } = require('@aws-sdk/credential-provider-node');

const app = express();
const PORT = 3001;

// Configuration
const AGENT_ARN = 'arn:aws:bedrock-agentcore:us-east-1:611291728384:runtime/cfn_mcp_server-4KOBaDFd4a';
const REGION = 'us-east-1';
const SERVICE = 'bedrock-agentcore';

// Encode ARN for URL
function encodeArn(arn) {
  return arn.replace(/:/g, '%3A').replace(/\//g, '%2F');
}

// Get MCP endpoint URL
function getMcpUrl() {
  const encodedArn = encodeArn(AGENT_ARN);
  return `https://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/${encodedArn}/invocations?qualifier=DEFAULT`;
}

// Middleware
app.use(cors());
app.use(express.json());

// Session storage
const sessions = new Map();

// Proxy endpoint
app.post('/api/mcp', async (req, res) => {
  try {
    const mcpRequest = req.body;
    const sessionId = req.headers['x-session-id'];
    
    console.log('Received MCP request:', JSON.stringify(mcpRequest, null, 2));
    
    // Get AWS credentials
    const credentials = await defaultProvider()();
    
    // Prepare request
    const url = new URL(getMcpUrl());
    const body = JSON.stringify(mcpRequest);
    
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Host': url.host,
    };
    
    // Add session ID if provided
    if (sessionId) {
      headers['Mcp-Session-Id'] = sessionId;
    }
    
    // Create HTTP request for signing
    const request = new HttpRequest({
      method: 'POST',
      protocol: url.protocol,
      hostname: url.hostname,
      path: url.pathname + url.search,
      headers,
      body,
    });
    
    // Sign request with SigV4
    const signer = new SignatureV4({
      credentials,
      region: REGION,
      service: SERVICE,
      sha256: Sha256,
    });
    
    const signedRequest = await signer.sign(request);
    
    console.log('Signed request headers:', signedRequest.headers);
    
    // Make request to AgentCore
    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: signedRequest.headers,
      body: signedRequest.body,
    });
    
    console.log('AgentCore response status:', response.status);
    
    // Extract new session ID if present
    const newSessionId = response.headers.get('Mcp-Session-Id');
    if (newSessionId) {
      res.setHeader('X-Session-Id', newSessionId);
    }
    
    // Forward response
    const data = await response.json();
    console.log('AgentCore response:', JSON.stringify(data, null, 2));
    res.json(data);
    
  } catch (error) {
    console.error('Proxy error:', error);
    res.status(500).json({
      error: error.message,
      details: error.stack,
    });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    agentArn: AGENT_ARN,
    region: REGION,
    mcpUrl: getMcpUrl(),
  });
});

app.listen(PORT, () => {
  console.log(`🚀 Backend proxy running on http://localhost:${PORT}`);
  console.log(`📡 Proxying to: ${getMcpUrl()}`);
  console.log(`🔐 Using AWS credentials from environment`);
});
