# Cold Start & Pre-Warm Research – CFN Builder

Research on whether pre-warming, cold-start mitigation, or similar strategies can further reduce response time for the CFN builder flow (WebSocket → Lambda → AgentCore → Bedrock Converse).

---

## Where Time Is Spent

| Stage | Typical latency | Cold start? |
|-------|------------------|-------------|
| WebSocket → Lambda (first) | ~50–100 ms | Lambda cold start possible |
| Lambda async self-invoke | ~100–200 ms | — |
| Lambda → AgentCore (HTTP) | ~200–500 ms | AgentCore container cold start possible |
| AgentCore → MCP → Bedrock Converse | ~15–40 s | Dominated by inference, not cold start |
| Bedrock (after idle) | — | Some reports: 1–1.5 min delay after ~10 min idle |

Most of the 25–45 s you see today is **Bedrock inference** (architecture + template). Cold start and pre-warm mainly affect the first request after idle and add at most a few seconds (Lambda + AgentCore).

---

## 1. Lambda Cold Start

**What happens:** First request (or after scale-to-zero) pays init time (load code, run global/import code). Often **~200–800 ms** for Python, depending on memory and package size.

**Pre-warm / mitigation:**

- **Provisioned Concurrency**  
  - Keeps a fixed number of execution environments warm (e.g. 1–2).  
  - First request and subsequent ones avoid cold start.  
  - **Cost:** Extra charge for provisioned capacity (~\$10–20+/month per provisioned instance, depending on region and memory).  
  - **Implementation:** Add a version/alias to the WebSocket Lambda and attach `AWS::Lambda::ProvisionedConcurrencyConfig` (see [PERFORMANCE_ANALYSIS.md](./PERFORMANCE_ANALYSIS.md) Strategy 7).  
  - **Worth it?** Only if you care about shaving a few hundred ms on the **first** request; the long pole is still Bedrock.

- **Other:** Keep deployment package small, avoid heavy imports at top level. Already reasonable for the current handler.

**Recommendation:** Optional. Use Provisioned Concurrency only if you have a hard requirement for sub-second first request (e.g. demo). For normal “Generate” flows, Lambda cold start is a small fraction of total time.

---

## 2. AgentCore (MCP Container) Cold Start

**What happens:** AgentCore runs the MCP server in a container (microVM per session). First request after idle can pay **~2–5 s** for container start; subsequent requests reuse the session and are much faster.

**Lifecycle (from AWS docs):**

- `idleRuntimeSessionTimeout`: default **900 s** (15 min). After 15 min with no traffic, the session (and its microVM) can be torn down.
- `maxLifetime`: default **28,800 s** (8 h). Max lifetime of an instance.

So after 15+ minutes of no tool calls, the next call may hit a new microVM and see a 2–5 s cold start.

**Pre-warm options:**

- **Increase idle timeout**  
  - Set `idleRuntimeSessionTimeout` (and optionally `maxLifetime`) in AgentCore lifecycle config so sessions stay alive longer.  
  - Reduces how often you hit cold start; does not “pre-warm” from zero.

- **Scheduled keep-alive ping**  
  - EventBridge rule (e.g. every 5–10 min) invokes a small Lambda that calls AgentCore with a no-op or cheap tool (e.g. a “ping” tool that returns immediately).  
  - Requires: (1) a stable way to target the same runtime/session (e.g. fixed `runtimeSessionId` if your integration supports it), and (2) a no-op tool or very light tool on the MCP server.  
  - Our current Lambda calls AgentCore **without** a persistent `runtimeSessionId` (it uses the MCP invocations endpoint). So “same session” behavior may depend on how AgentCore maps invocations to sessions.  
  - More complex to implement and operate; only worth it if you need to guarantee “no cold start” after idle.

**Recommendation:** Start with defaults. If you see clear 2–5 s spikes only on the first request after long idle, consider increasing `idleRuntimeSessionTimeout` (e.g. 30 min). Explore keep-alive only if you have strict latency SLAs after idle.

---

## 3. Bedrock Converse – Latency-Optimized Inference

**What it is:** Bedrock supports a **latency-optimized** inference tier. You pass `performanceConfig: { latency: "optimized" }` in the Converse request to get lower latency when that tier is available for the model/region.

**Converse API:** The Converse API supports a top-level **`performanceConfig`** with **`latency`** (`"standard"` \| `"optimized"`). So you can add:

```python
kwargs["performanceConfig"] = {"latency": "optimized"}
```

to your `bedrock.converse(**kwargs)` call when you want to use the optimized tier.

**Region/model support (as of docs):**

- **us-east-1:** Latency-optimized for **Amazon Nova Pro** (e.g. `amazon.nova-pro-v1:0`).  
- **us-east-2 / us-west-2:** Latency-optimized for **Claude 3.5 Haiku**, Llama 3.1 70B/405B (and cross-region inference profiles).

We currently use **us-east-1** and **Claude Haiku 4.5** (`global.anthropic.claude-haiku-4-5-20251001-v1:0`). Latency-optimized for **Claude 3.5 Haiku** is listed in us-east-2 and us-west-2, not us-east-1. So for the current stack (us-east-1 + Haiku 4.5), **latency-optimized may not be available** for this model; the API may ignore it or fall back to standard.

**If you switch region or model:**

- In **us-east-2** or **us-west-2**, you could use Claude 3.5 Haiku with an inference profile and `performanceConfig: { "latency": "optimized" }` for faster inference.  
- In **us-east-1**, you could try Nova Pro with latency-optimized if you’re open to a different model.

**Recommendation:** Add **`performanceConfig`** to your Converse helper so it’s easy to enable when supported (e.g. env flag or per-call). For current us-east-1 + Haiku 4.5, set it to `"optimized"` only if you confirm in the Bedrock console/docs that this model/region supports it; otherwise leave as `"standard"` or omit.

---

## 4. Bedrock “Cold Start” After Idle

Some users report **much longer delays (e.g. 1–1.5 min)** on the first Converse request after ~10 minutes of no traffic. That’s likely model/infrastructure warm-up on the Bedrock side, not something you can pre-warm from the application.

**Mitigation:** No application-level pre-warm. If you need consistent low latency after idle, options are:

- Use **Provisioned Throughput** (if available for your model) for dedicated capacity.  
- Or accept that the very first request after long idle may be slow and document it.

---

## Summary: What Can Actually Speed You Up

| Strategy | Effect | Effort | Cost | Use it? |
|----------|--------|--------|------|--------|
| **Lambda Provisioned Concurrency** | Removes Lambda cold start (~200–800 ms on first request) | Low (config + version/alias) | ~\$10–20+/mo per instance | Optional; only for “first request” and demos |
| **AgentCore longer idle timeout** | Fewer container cold starts after 15 min idle (saves ~2–5 s when it would have happened) | Low (lifecycle config) | None | Yes, if you see cold starts after idle |
| **AgentCore keep-alive ping** | Can keep one session warm; only helps if invocations reuse that session | High (scheduler + Lambda + possibly MCP ping tool + session id handling) | Low | Only for strict “no cold start” SLAs |
| **Bedrock `performanceConfig.latency = "optimized"`** | Lower inference latency where supported | Low (add param to Converse) | Same or different pricing (see Bedrock pricing) | Yes in us-east-2/us-west-2 for Claude 3.5 Haiku; in us-east-1 only if supported for your model |
| **Bedrock after-idle delay** | No app-level pre-warm | — | — | Accept or use Provisioned Throughput if needed |

**Biggest gains already in place:** Shorter prompts, no thinking on architecture/template, and smaller `max_tokens` for template. The next meaningful levers are (1) Bedrock latency-optimized where available, and (2) optional Lambda provisioned concurrency if you need the first request to be as fast as the rest.

---

## Optional Code Change: Add `performanceConfig` to Converse

So that you can enable latency-optimized when the model/region supports it (e.g. after switching to us-east-2 or a supported inference profile), you can add:

```python
# In converse_with_retry(), when building kwargs:
if os.environ.get("BEDROCK_LATENCY_OPTIMIZED", "").lower() == "true":
    kwargs["performanceConfig"] = {"latency": "optimized"}
```

Then set `BEDROCK_LATENCY_OPTIMIZED=true` only in environments where you use a model/region that supports it (e.g. Claude 3.5 Haiku in us-east-2).
