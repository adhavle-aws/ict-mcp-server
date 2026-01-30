# CloudFormation Builder UI

Simple web UI for CloudFormation MCP Server.

## Setup

```bash
cd backend
npm install
```

## Run

### Start Backend
```bash
cd backend
npm start
```

Backend runs on `http://localhost:3001`

### Open Frontend
```bash
open frontend/index.html
```

Or serve with:
```bash
cd frontend
python3 -m http.server 3000
```

Then open `http://localhost:3000`

## Usage

1. Enter natural language prompt (e.g., "Create an S3 bucket with versioning")
2. Click "Build Template with Claude"
3. Review generated CloudFormation template
4. Click "Validate Template"
5. Enter stack name
6. Click "Provision Stack"

Done! 🚀
