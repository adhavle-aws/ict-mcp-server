# Timeout limits in the flow

End-to-end path: **Browser** → **WebSocket** → **API Gateway** → **Lambda** (sync return) → **Lambda** (async) → **AgentCore** → **MCP tools**.

| Layer | Limit | Notes |
|-------|--------|------|
| **Browser (client)** | **5 min (300 s)** | `callMcpTool` promise rejects after this if no response. Increased from 2 min so long tool runs (e.g. generate + template) can complete. |
| **API Gateway WebSocket** | **29 s** | Fixed AWS limit for Lambda integration *response*. We avoid it: Lambda returns in &lt;1 s and invokes itself asynchronously; the async invocation does the real work and uses `post_to_connection` to send the result. |
| **Lambda (first invocation)** | Returns in &lt;1 s | Only forwards to async invoke and returns. |
| **Lambda (second invocation)** | **10 min (600 s)** | `Timeout: 600` in `websocket-infrastructure.yaml`. Max time for the async run (AgentCore call + post_to_connection). |
| **Lambda → AgentCore HTTP** | **5 min (300 s)** | `urllib.request.urlopen(..., timeout=300)` in `handler.py`. Request to Bedrock AgentCore. |
| **AgentCore / Bedrock** | Service limits | Model invoke and runtime limits apply; no extra timeout in our code. |
| **CloudFormation** | N/A | CreateStack/UpdateStack is asynchronous. UI polls stack events every 3 s; no timeout for “stack complete.” |

**Practical limit for a single tool call (e.g. Generate, Validate, Provision):** the **browser 5 min** and the **Lambda→AgentCore 5 min** are aligned; the Lambda function timeout (10 min) is higher so the async path has headroom. If a tool regularly needs more than 5 minutes, increase the `timeout` in `handler.py` (urlopen) and the Lambda `Timeout` in the template, and increase the client timeout in the UI (e.g. to 600 s).
