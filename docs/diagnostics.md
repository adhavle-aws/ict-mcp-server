# E2E flow diagnostics and bottleneck analysis

This doc describes the end-to-end request path, where timing is logged, and where the bottleneck usually is.

---

## 1. E2E stages (in order)

| Stage | Where | Typical duration | Log location |
|-------|--------|------------------|--------------|
| **1. UI → WebSocket** | Browser / Salesforce | &lt;100 ms | (client-side; no server log) |
| **2. API Gateway $default** | API Gateway → Lambda (first invoke) | &lt;200 ms | Lambda: `Route: $default`, `Duration` in REPORT |
| **3. Lambda async invoke** | Lambda invokes itself (Event) | &lt;100 ms | (no separate log; first invoke returns quickly) |
| **4. AgentCore HTTP** | Lambda → AgentCore (HTTPS `tools/call`) | **~30–70+ s** for Bedrock tools | Lambda: `[E2E] Lambda: AgentCore HTTP wait=...s` |
| **5. MCP tool** | AgentCore → mcp_server.py | Same as 4 | AgentCore logs: `[E2E] <tool> | bedrock_invoke: ...s` |
| **6. Bedrock invoke_model** | Inside MCP tool | **~30–65 s** (main cost) | AgentCore: `[E2E] <tool> | bedrock_invoke: ...s` |
| **7. Lambda → WebSocket** | post_to_connection | &lt;500 ms | Lambda REPORT total |

So end-to-end for “Generate Infrastructure” (overview + template) you see roughly:

- **First tool (overview):** Lambda async ~(0.1s + **AgentCore round-trip 30–70s** + 0.5s) → **bottleneck = AgentCore round-trip**, which is almost entirely **Bedrock inference** inside the MCP tool.
- **Second tool (template):** Same; again **Bedrock** dominates.
- **AgentCore ~60s limit:** If a single tool call exceeds ~60s, AgentCore returns an empty body and Lambda reports “Empty response from AgentCore”.

---

## 2. Where the bottleneck is

- **Primary bottleneck:** **Bedrock `invoke_model`** inside the MCP tools `generate_architecture_overview` and `build_cfn_template`. That call is 30–70+ seconds depending on prompt size and output length. Everything else (WebSocket, API Gateway, Lambda, AgentCore routing) is sub-second or a few seconds.
- **Hard limit:** **AgentCore ~60s** per MCP tool invocation. If Bedrock takes longer than that, the request is cut off and the client sees “Empty response from AgentCore”.
- **API Gateway 29s:** We avoid it by not waiting for AgentCore in the first Lambda invocation (async pattern).

So in practice:

- **E2E latency** ≈ time for one or two Bedrock calls (overview + template).
- **Failures** when a single tool runs &gt;60s → need AgentCore async/long-running pattern or faster/smaller model to stay under 60s. `build_cfn_template` is tuned to stay under 60s (Haiku, no thinking, max_tokens=16384, optional `BUILD_CFN_FAST=true` to skip schema hints).

---

## 3. How to read the logs

### Lambda (async invocation)

- **Log group:** `/aws/lambda/cfn-builder-websocket`
- **What to look for:**
  - `[E2E] Lambda: AgentCore HTTP wait=Xs response_len=Y` → time Lambda spent waiting on AgentCore and size of response (0 = empty, timeout).
  - `[E2E] Lambda async: AgentCore round-trip=Xs total_async=Ys tool=<name>` → same round-trip in the async path.
  - `Response data length: 0` → empty response (often after ~60s = AgentCore timeout).

**Example (success):**

```
Async processing: generate_architecture_overview, requestId: 123
[E2E] Lambda: AgentCore HTTP wait=45.2s response_len=3200
[E2E] Lambda async: AgentCore round-trip=45.3s total_async=45.5s tool=generate_architecture_overview
```

**Example (timeout):**

```
Async processing: generate_architecture_overview, requestId: 456
Response data length: 0
Response starts with:
[E2E] Lambda async: AgentCore round-trip=67.7s ...
```

### AgentCore runtime (MCP server)

- **Log group:** `/aws/bedrock-agentcore/runtimes/cfn_mcp_server-4KOBaDFd4a-DEFAULT`
- **What to look for:**
  - `[E2E] generate_architecture_overview | setup: Xs` → MCP setup (client, etc.).
  - `[E2E] generate_architecture_overview | bedrock_invoke: Xs` → **Bedrock call duration (main cost).**
  - `[E2E] generate_architecture_overview | total: Xs | output_tokens~N` → total tool time and rough output size.
  - `[build_cfn_template] WARNING: response truncated` → template hit max_tokens; tool result includes `truncated: true`.

**Example:**

```
[E2E] generate_architecture_overview | setup: 0.01s
[E2E] generate_architecture_overview | bedrock_invoke: 44.2s
[E2E] generate_architecture_overview | total: 44.3s | output_tokens~420
```

**Tail AgentCore logs (us-east-1, profile aws-gaurav):**

```bash
# Last 30 min, follow
aws logs tail /aws/bedrock-agentcore/runtimes/cfn_mcp_server-4KOBaDFd4a-DEFAULT \
  --since 30m --follow --region us-east-1 --profile aws-gaurav

# Last 1 hour, filter for build_cfn_template and truncation
aws logs filter-log-events \
  --log-group-name /aws/bedrock-agentcore/runtimes/cfn_mcp_server-4KOBaDFd4a-DEFAULT \
  --start-time $(($(date +%s) - 3600))000 \
  --filter-pattern "build_cfn_template" --region us-east-1 --profile aws-gaurav
```

---

## 4. Truncation (template cut off)

- If the CloudFormation template is cut off but **Validate** still passes, the UI may be showing only part of the template (e.g. character limit), or the model hit **max_tokens** and Bedrock truncated the response.
- The MCP server now sets `truncated: true` and `truncation_reason` in the tool result when Bedrock returns `stopReason: max_tokens` (or `length`). It also logs `[build_cfn_template] WARNING: response truncated`.
- **max_tokens** for `build_cfn_template` is 32768; increase in `mcp_server.py` if large templates still truncate.
- Check AgentCore logs (commands above) for the WARNING line and for `output_lines=N` in the total-timing line to see how much was returned.

---

## 5. Quick checklist for “slow” or “empty” responses

1. **Lambda logs**  
   Check `AgentCore HTTP wait` and `response_len`. If wait is ~60s and `response_len=0` → AgentCore timeout.

2. **AgentCore logs**  
   Check `bedrock_invoke` duration. If it’s &gt;60s → tool will hit AgentCore limit; consider faster model, fewer tokens, or async pattern.

3. **Two tools in sequence**  
   “Generate Infrastructure” = overview then template; total E2E ≈ sum of two Bedrock calls (no way to parallelize from a single “Generate” click today).

4. **Cold start**  
   First request after idle can add a few seconds (Lambda or AgentCore); later requests reflect steady-state bottleneck (Bedrock).

---

## 6. Summary

| Question | Answer |
|----------|--------|
| Where is time spent? | Mostly in **Bedrock** inside the MCP tools (overview + template). |
| What limits E2E? | **Bedrock latency** (~30–70s per call) and **AgentCore ~60s** per tool. |
| How to confirm? | Lambda: `[E2E] Lambda: AgentCore HTTP wait=...`; AgentCore: `[E2E] <tool> \| bedrock_invoke: ...`. |
| How to improve? | Faster/smaller model, fewer tokens, or AgentCore long-running/async so tools return quickly and complete in background. |
