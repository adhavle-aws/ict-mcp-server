# AWS Architect AI - Salesforce Deployment

## Overview

Deploy the AWS Architect AI application as a Visualforce page in your Salesforce org.

## Files

- `AWSArchitectAI.page` - Visualforce page with embedded UI
- `AWSArchitectAI.page-meta.xml` - Metadata for deployment

## Deployment Steps

### 1. Via Salesforce UI (Easiest)

1. Go to **Setup** → **Visualforce Pages**
2. Click **New**
3. Label: `AWS Architect AI`
4. Name: `AWSArchitectAI`
5. Copy content from `AWSArchitectAI.page`
6. Click **Save**

### 2. Via Salesforce CLI

```bash
# Install Salesforce CLI
npm install -g @salesforce/cli

# Authenticate
sf org login web --alias myorg

# Deploy
sf project deploy start --source-dir salesforce_ui/
```

### 3. Via VS Code (Salesforce Extension)

1. Install "Salesforce Extension Pack" in VS Code
2. Authorize your org
3. Right-click `salesforce_ui/` folder
4. Select "Deploy Source to Org"

## Access the App

After deployment, access at:
```
https://orgfarm-734a8e4b92-dev-ed.develop.my.salesforce.com/apex/AWSArchitectAI
```

Or add to Salesforce navigation:
1. **Setup** → **App Manager**
2. Edit your app
3. Add **Visualforce Tab** → Select `AWSArchitectAI`

## Features

All features from the web version:
- ✅ Architecture Overview with ASCII diagrams
- ✅ Well-Architected Framework Review
- ✅ Cost Optimization Analysis
- ✅ CloudFormation Template Generation
- ✅ Template Validation
- ✅ Example Prompt (Quoting Agent)
- ✅ Tool timings (per-tool elapsed time under Generate button)
- ✅ Thinking/reasoning in console when backend returns it

## Security

The app connects to:
- WebSocket API: `wss://z832i481e5.execute-api.us-east-1.amazonaws.com/prod`
- Backend: AWS Lambda with IAM authentication
- MCP Server: AgentCore Runtime (serverless)

No Salesforce data is sent to AWS - only infrastructure requirements.

## Customization

To customize for your org:
1. Edit `AWSArchitectAI.page`
2. Update branding, colors, or layout
3. Redeploy

## Support

For issues:
- Check browser console for errors
- Verify WebSocket connection
- Ensure internet access from Salesforce

---

**Status**: Ready to deploy to Salesforce org
