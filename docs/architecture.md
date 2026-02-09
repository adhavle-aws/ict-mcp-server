# Architecture: AWS Architect MCP (CloudFormation Builder)

This document describes the end-to-end architecture, the exact request flow, where and how MCP tools are invoked, and the timeout fix for long-running tool calls.

---

## 1. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  UIs (clients)                                                                   │
│  ┌──────────────────────┐    ┌──────────────────────┐                            │
│  │  Standalone (Amplify)│    │  Salesforce UI       │                            │
│  │  index.html          │    │  AWSArchitectAI.page  │                            │
│  └──────────┬───────────┘    └──────────┬───────────┘                            │
└─────────────┼──────────────────────────┼───────────────────────────────────────┘
              │                          │
              │  WebSocket (wss://…)     │  same WebSocket or direct to AgentCore
              ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  API Gateway (WebSocket API)                                                     │
│  • Routes: $connect, $disconnect, $default                                       │
│  • Integration timeout: 29 seconds (fixed)                                       │
└─────────────────────────────────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Lambda (cfn-builder-websocket)                                                  │
│  • Receives WebSocket messages on $default                                       │
│  • Returns 200 immediately; async invokes itself for actual MCP call              │
│  • Second invocation: calls AgentCore, then post_to_connection with result        │
└─────────────────────────────────────────┬───────────────────────────────────────┘
              │
              │  HTTPS + SigV4 (tools/call)
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Amazon Bedrock AgentCore Runtime                                                │
│  • Hosts the MCP server container (mcp_server.py)                                 │
│  • Invocation URL: …/runtimes/{agentArn}/invocations?qualifier=DEFAULT            │
└─────────────────────────────────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  MCP Server (mcp_server.py)                                                      │
│  • FastMCP, stateless_http=True (required for AgentCore)                         │
│  • Tools call AWS APIs (CloudFormation, Bedrock, etc.) using env credentials      │
└─────────────────────────────────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  AWS APIs                                                                        │
│  • CloudFormation (create_stack, describe_stacks, describe_stack_events, …)       │
│  • Bedrock (invoke_model for overview/template generation)                        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

- **Standalone UI**: Served by AWS Amplify (on git push). Connects to a WebSocket URL (API Gateway) to call MCP tools.
- **Salesforce UI**: Visualforce page that uses the same WebSocket (or can be configured to call AgentCore directly with IAM). Same `callMcpTool(toolName, args)` pattern.
- **AgentCore**: Runs the MCP server as a container; IAM role for the runtime is configured in `.bedrock_agentcore.yaml` (e.g. `AmazonBedrockAgentCoreSDKRuntime-…`). Stacks are created in the AgentCore account/region.

---

## 2. Exact request flow (where MCP tools are called)

### 2.1 User action in the UI

1. User performs an action (e.g. “Generate Infrastructure”, “Validate”, “Deploy”, “Check status”, “Delete stack”).
2. UI JavaScript calls **`callMcpTool(toolName, args)`** with the appropriate tool name and arguments.

### 2.2 `callMcpTool` (frontend)

- **Location**: `ui/frontend/index.html` (and mirrored in `salesforce_ui/force-app/.../AWSArchitectAI.page`).
- **Behavior**:
  - Assumes a WebSocket `ws` is already connected to the API Gateway WebSocket URL (e.g. `wss://9h32jjkhg3.execute-api.us-east-1.amazonaws.com/prod`).
  - Generates a `requestId`, stores a promise callback in `requestCallbacks`, and sends one JSON message:
    ```json
    { "id": "<requestId>", "tool": "<toolName>", "arguments": { ... } }
    ```
  - Waits (up to 5 minutes) for a WebSocket message with the same `requestId` and `type`: `response` (resolve with `data`) or `error` (reject).
  - Progress messages (`type: 'progress'`) are logged but do not resolve the promise.

So **every MCP tool call from the UI goes over WebSocket** as a single request; the response comes back asynchronously on the same connection.

### 2.3 API Gateway → Lambda ($default)

- **Location**: API Gateway WebSocket API routes the message to the Lambda function (e.g. `cfn-builder-websocket`).
- **Handler**: `deploy/lambda_websocket/handler.py` (or inline in `deploy/websocket-infrastructure.yaml`).
- **Route**: `$default` (body contains `id`, `tool`, `arguments`).

Lambda does **not** call AgentCore in this first invocation. It:

1. Parses `id`, `tool`, `arguments` from the body.
2. Sends **acknowledged** and **progress** messages back over the WebSocket (via `post_to_connection`).
3. **Asynchronously invokes itself** with `InvocationType='Event'` and a payload that includes:
   - `async_processing`: `{ tool, arguments, requestId, connectionId, event }`.
4. **Returns 200** to API Gateway immediately (well under 29 seconds).

So **MCP tools are not called in the request that API Gateway is waiting on**. They are called in a **second, asynchronous** Lambda invocation.

### 2.4 Second Lambda invocation (async)

- **Trigger**: Same Lambda, invoked asynchronously with `async_processing` in the payload.
- **Behavior**:
  1. Sends a **progress** message (“Processing &lt;tool&gt;…”).
  2. Calls **`call_mcp_tool(tool, arguments)`**:
     - Builds the AgentCore invocation URL from `AGENT_ARN` and region.
     - Sends an HTTPS POST (SigV4-signed) with JSON-RPC body: `method: "tools/call"`, `params: { name: tool_name, arguments }`.
     - Waits for the response (timeout 300s in handler).
  3. Parses the MCP response (SSE format: `data: {...}`), extracts the tool result JSON.
  4. Sends a WebSocket message with `type: 'response'`, `requestId`, `tool`, `data`, `status: 'completed'` (or `type: 'error'` on failure).

So **MCP tools are called only here**: inside the async Lambda, via **AgentCore’s `tools/call` invocation**. The MCP server (`mcp_server.py`) runs in AgentCore; each tool is implemented as a function decorated with `@mcp.tool()`.

### 2.5 AgentCore → MCP server

- AgentCore routes the `tools/call` request to the correct runtime (by ARN).
- The runtime runs `mcp_server.py`; the FastMCP framework dispatches to the tool function by name (e.g. `provision_cfn_stack`, `get_cfn_stack_events`).
- The tool uses `get_cfn_client()`, `get_bedrock_client()`, etc., with the runtime’s IAM role (e.g. `AmazonBedrockAgentCoreSDKRuntime-…` in the account where AgentCore is deployed).
- Return value is serialized and sent back in the SSE response; Lambda forwards it to the UI as `message.data`.

---

## 3. Timeout fix (29 seconds)

### 3.1 Problem

- **API Gateway** WebSocket integration has a **29-second maximum**: if the Lambda that handles the WebSocket message does not return within 29 seconds, API Gateway closes the connection and the client sees a timeout.
- **AgentCore** MCP tool calls (e.g. `generate_architecture_overview`, `build_cfn_template`) can take **~60+ seconds** (Bedrock inference, template generation).
- If Lambda waited for AgentCore inside the request that API Gateway is waiting on, the integration would hit the 29s limit and the user would get a timeout even though the tool would eventually complete.

### 3.2 Fix: Async Lambda (current behavior)

- The **first** Lambda invocation (the one that API Gateway waits on) **never** waits for AgentCore. It:
  - Sends ack/progress.
  - Starts the **async** second invocation.
  - Returns **200** in under a second.
- The **second** invocation runs with no 29s limit; it calls AgentCore (as long as needed, e.g. 300s timeout in code) and then uses **API Gateway Management API** (`post_to_connection`) to push the result over the **same** WebSocket connection.
- The WebSocket connection remains open (API Gateway idle timeout is much longer than 29s), so the client receives the response when the async invocation finishes.

So the **timeout fix** is: **do not wait for MCP inside the request that API Gateway is timing**. Run the MCP call in a separate, asynchronous Lambda invocation and stream the result back over the WebSocket.

Reference: `deploy/TIMEOUT_FIX.md` (Fix 1 = async Lambda; Fix 2 = bypass API Gateway with an HTTPS backend proxy).

### 3.3 AgentCore ~60s MCP tool timeout and "Empty response from AgentCore"

- **Symptom:** Lambda (or client) reports **"Empty response from AgentCore"** and the tool call took ~60+ seconds.
- **Cause:** Bedrock AgentCore Runtime enforces an **~60-second timeout** on MCP tool invocations. If a tool runs longer (e.g. `generate_architecture_overview` or `build_cfn_template` calling Bedrock for ~68s), the runtime closes the request and returns no body, so the Lambda sees `response_data` empty and returns this error.
- **Logs:** In Lambda: `Response data length: 0`, `Response starts with:` (empty). In AgentCore runtime logs: `CallToolRequest` followed later by process/server restart messages.
- **Fix:** For tools that can exceed ~60s, use the [AgentCore long-running / async pattern](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html) (e.g. start work in background, return quickly, complete asynchronously). Do not block the MCP handler until Bedrock returns.

---

## 4. MCP tools: list and where they are called

All tools are defined in **`mcp_server.py`** with `@mcp.tool()`. The following table lists each tool and where the **UI** calls it (same pattern in standalone and Salesforce UIs unless noted).

| MCP tool | Purpose | Where called (UI flow) |
|----------|----------|------------------------|
| `generate_architecture_overview` | Bedrock-generated text overview from a prompt | **Generate Infrastructure** → Step 1 (architecture tab). |
| `build_cfn_template` | Bedrock-generated CloudFormation template (YAML/JSON) from same prompt | **Generate Infrastructure** → Step 2 (template tab). |
| `validate_cfn_template` | Validate template (optional auto-fix). | **Validate Template** button; also before **Deploy** (validation step). |
| `provision_cfn_stack` | Create or update stack (template, params, capabilities). Tags new stacks with `stack-creator=aws-architect-mcp`. | **Deploy** flow after validation. |
| `get_cfn_stack_events` | Describe stack status, recent events, and outputs. | **Deploy** (initial status + polling until complete); **Check status**; **Delete stack** (poll until stack gone). |
| `delete_cfn_stack` | Start stack deletion. | **Delete stack** button. |
| `generate_architecture_diagram` | Generate diagram from template (e.g. PNG). | Available for diagram generation from template (if wired in UI). |
| `analyze_cost_optimization` | Cost analysis from prompt or template. | Available for cost analysis (if wired in UI). |
| `well_architected_review` | Well-Architected review from prompt or template. | Available for WAF review (if wired in UI). |
| `test_delay` | Test long-running behavior (e.g. 80s delay). | For testing timeout/async behavior only. |

**Flow summary:**

- **Generate**: `generate_architecture_overview` → `build_cfn_template` (both via `callMcpTool`).
- **Validate**: `validate_cfn_template`.
- **Deploy**: `validate_cfn_template` (if not already valid) → `provision_cfn_stack` → repeated `get_cfn_stack_events` until stack is in a terminal state; then outputs are shown.
- **Check status / Delete**: `get_cfn_stack_events` and/or `delete_cfn_stack`, then polling with `get_cfn_stack_events`.

---

## 5. Stack tagging

- Stacks **created** by the MCP (not updated) are tagged with:
  - **Key:** `stack-creator`
  - **Value:** `aws-architect-mcp`
- This is set in **`provision_cfn_stack`** in `mcp_server.py` (only when `create_stack` is used; `update_stack` does not send tags so existing tags are preserved).
- Use: identify stacks created by this MCP in billing, Resource Groups, and DevOps Agent topology. Optionally, add the same tag to resources inside the template for resource-level visibility.

---

## 6. Deployment and configuration

| Component | How it’s deployed / configured |
|-----------|---------------------------------|
| **MCP server** | `./deploy-agentcore.sh` (or `agentcore launch`). Uses `mcp_server.py` and `.bedrock_agentcore.yaml`. |
| **Lambda + WebSocket API** | `deploy/websocket-infrastructure.yaml` (or equivalent) with `AgentArn` parameter. Lambda env: `AGENT_ARN`, `REGION`. |
| **Standalone UI** | Amplify (build on git push). WebSocket URL in `index.html` (e.g. `WS_URL`). |
| **Salesforce UI** | `sf project deploy start` from `salesforce_ui/`. Same WebSocket or AgentCore endpoint config as needed. |
| **AgentCore runtime IAM** | Role in account (e.g. `AmazonBedrockAgentCoreSDKRuntime-…`). Permissions: CloudFormation, Bedrock, and any other services the MCP tools use (see `deploy/agentcore-full-policy.json` or attached policies). |

---

## 7. References

- **Timeout fix details**: `deploy/TIMEOUT_FIX.md`
- **Lambda WebSocket handler**: `deploy/lambda_websocket/handler.py`
- **WebSocket infrastructure**: `deploy/websocket-infrastructure.yaml`
- **MCP server**: `mcp_server.py`
- **Standalone UI**: `ui/frontend/index.html`
- **Salesforce UI**: `salesforce_ui/force-app/main/default/pages/AWSArchitectAI.page`
