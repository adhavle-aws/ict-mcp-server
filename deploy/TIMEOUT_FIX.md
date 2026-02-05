# API Gateway 29s Timeout vs AgentCore ~68s Response

## Root cause

- **API Gateway WebSocket** has a **29-second maximum integration timeout**. The Lambda that handles a WebSocket message **must return** within 29 seconds or the connection is closed and the client sees a timeout.
- **AgentCore Runtime** MCP tool calls (e.g. `build_cfn_template`, `generate_architecture_overview`) take **~68 seconds** wall time.
- So: **Lambda runs 68s → API Gateway stops waiting at 29s → timeout.**

Flow today:

```
Browser → WebSocket → API Gateway (29s max) → Lambda → AgentCore (~68s)
                          ↑
                    Request times out here
```

## Fix 1: Async Lambda (current WebSocket path)

Keep using WebSocket + API Gateway, but **never** wait for AgentCore inside the request that API Gateway is waiting on:

1. On `$default`: Lambda **returns 200 immediately** after sending an ack/progress and **asynchronously invoking itself** (`InvocationType='Event'`).
2. A **second** Lambda invocation runs in the background, calls AgentCore (~68s), then uses **API Gateway Management API** (`post_to_connection`) to push the result back over the same WebSocket.
3. The WebSocket connection stays open (API Gateway idle timeout is ~10 minutes), so the client can receive the response when the async invocation finishes.

So:

- **First invocation:** returns in &lt;1s → no 29s timeout.
- **Second invocation:** runs as long as needed; it only talks to AgentCore and then to `post_to_connection`, neither of which has a 29s limit.

**Implementation:** The inline Lambda in `websocket-infrastructure.yaml` already uses this async pattern. The standalone `lambda_websocket/handler.py` has been updated to use the same pattern so that a deployment that packages `handler.py` (e.g. via `package.sh`) also gets async behavior.

If you deploy using a zip built from `handler.py`, set the Lambda **Handler** to `handler.lambda_handler` (the template’s inline code uses `index.lambda_handler`). The Lambda execution role must allow `lambda:InvokeFunction` on itself so it can invoke the async path; `websocket-infrastructure.yaml` already grants this.

## Fix 2: Bypass API Gateway (HTTPS + Backend Proxy)

Remove WebSocket from the UI path so nothing in the chain has a 29s limit:

- **Frontend** → HTTPS POST → **Backend Proxy** (e.g. `ui/backend_python/server.py`) → SigV4 → **AgentCore**.
- Host the Backend Proxy behind **ALB + ECS/EC2** (or run it locally). ALB and your server do not enforce a 29s limit.

See `.kiro/specs/ui-timeout-fix/` (requirements, design, tasks) for the full refactor: replace WebSocket with HTTPS in the UI and point the UI at the Backend Proxy.

## Summary

| Approach              | Change required                          | 29s limit |
|-----------------------|------------------------------------------|-----------|
| Async Lambda (Fix 1)  | Use async pattern in Lambda handler      | Avoided   |
| Backend Proxy (Fix 2) | UI calls Backend Proxy over HTTPS only   | Removed   |

For a **minimal change** with the existing WebSocket UI, use **Fix 1** (async Lambda). For a **long-term architecture** without API Gateway in the path, use **Fix 2** (Backend Proxy + HTTPS).
