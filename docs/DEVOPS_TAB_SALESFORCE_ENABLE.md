# Enabling DevOps Agent in the Salesforce UI Tab

This doc summarizes **demo-trigger**, **devops-service-api**, and how to expose them in the **DevOps Agent** tab on the Salesforce UI (`AWSArchitectAI.page`).

---

## 1. Folder: `demo-trigger`

**Purpose:** Trigger AWS DevOps Agent investigations for demos and testing.

| Item | Description |
|------|-------------|
| **Flow** | CloudWatch Alarm → SNS → Lambda → DevOps Agent webhook → Investigation. Optional: direct webhook (bypass alarm). |
| **.env** | `WEBHOOK_URL`, `WEBHOOK_SECRET` (from DevOps Agent webhook config). Copy `.env.example` to `.env`. |
| **Scripts** | |
| `setup_alb_unhealthy_alarm.sh` | One-time: create alarm, SNS, subscribe Lambda. |
| `trigger_alb_unhealthy_alarm.sh` | Set alarm to ALARM → SNS → Lambda → webhook → investigation. |
| `trigger_alb_unhealthy_webhook.sh` | Send incident payload directly to webhook (no AWS). |
| `generate_alb_traffic.sh` | Send traffic to ALB so CloudWatch has metrics. |
| `trigger_lambda_ecs_event.sh` | Simulate ECS event → Lambda → webhook. |
| `trigger_ecs_image_pull_failure.sh` | Simulate ECS image pull failure. |
| `trigger_bearer_token.sh` | Test webhook with bearer token auth. |
| **Salesforce-specific** | |
| `investigate_and_update_case.sh` | Send case number; DevOps Agent investigates and adds a comment to the **Salesforce Case**. Needs webhook + MCP so Agent can read/update Case. |
| `add_steering_to_incident.sh` | Add steering/instructions to an incident. |

**Docs:** `README-ALARM-TRIGGER.md` (architecture, demo steps, troubleshooting).

---

## 2. Folder: `devops-service-api`

**Purpose:** Connect the **Salesforce MCP Server** to the **AWS DevOps Agent** so DevOps Agent can use Salesforce (Cases, etc.) via MCP.

| Item | Description |
|------|-------------|
| **Flow** | DevOps Agent (MCP client) ↔ Salesforce MCP Server (OAuth 3LO) ↔ Salesforce org (Cases, SObjects). |
| **Scripts** | |
| `setup_cloudsmith_cli.sh` | Patch AWS CLI with CloudSmith control/data plane models (required first). |
| `create_devops_agent_space.sh` | Create an AWS DevOps Agent Space (e.g. `MyAgentSpace`). |
| `register_salesforce_mcp.sh` | Register Salesforce MCP Server with DevOps Agent (client-id, client-secret, agent-space-id). |
| `associate_salesforce_mcp.sh` | Associate the registered MCP with the Agent Space; select tools (e.g. `soql_query`, `create_sobject_record`, `update_sobject_record`). |
| **Salesforce side** | **Salesforce-DevOps-Setup.md**: Enable MCP Beta, create External Client App with callback `https://api.prod.cp.aidevops.us-east-1.api.aws/v1/register/mcpserver/callback`, then in DevOps Agent create MCP Server with endpoint `https://api.salesforce.com/platform/mcp/v1-beta.2/sandbox/sobject-all`, 3LO, scopes (api, sfap_api, refresh_token, einstein_gpt_api, offline_access). |

**Outcome:** DevOps Agent can query/update Salesforce (e.g. Cases) during investigations; `investigate_and_update_case.sh` then works end-to-end.

---

## 3. Current DevOps Agent Tab (Salesforce UI)

Today the tab shows:

- Short description of DevOps Agent (incident response, prevention, integrations).
- Buttons: “Open features” and “Open DevOps Agent console”.

It does **not** yet mention:

- How to connect DevOps Agent to Salesforce (devops-service-api).
- How to run demos (demo-trigger) or trigger investigations from Salesforce.

---

## 4. How to Enable This in the DevOps Agent Tab

### Option A: Add setup and demo instructions (no backend)

**In the Salesforce DevOps Agent tab:**

1. **“Connect DevOps Agent to Salesforce”**
   - Add a collapsible or sub-section with short steps from `devops-service-api` + `Salesforce-DevOps-Setup.md`:
     - Create Agent Space (`create_devops_agent_space.sh`).
     - In Salesforce: External Client App, callback URL for DevOps Agent.
     - Register and associate Salesforce MCP (`register_salesforce_mcp.sh`, `associate_salesforce_mcp.sh`).
   - Link or path to `devops-service-api/Salesforce-DevOps-Setup.md` (or host it and link).

2. **“Trigger a demo investigation”**
   - Add a short “Demo” subsection:
     - For **ALB unhealthy**: run `trigger_alb_unhealthy_alarm.sh` (link to repo or copy-paste).
     - For **Salesforce Case**: run `investigate_and_update_case.sh <case-number>` (requires webhook + MCP configured).
   - Link to `demo-trigger/README-ALARM-TRIGGER.md` for full flow.

**Pros:** No Apex/backend; safe; works with current deployment.  
**Cons:** Users run scripts locally or from a doc; no “one click” in the UI.

---

### Option B: “Trigger demo” from the UI (needs backend)

To let users **click a button** in the Salesforce DevOps tab and start a demo investigation:

1. **Webhook trigger**
   - DevOps Agent webhook is not callable from the browser (CORS, secrets). So the UI cannot call the webhook directly.
   - You need a **backend** that:
     - Is allowed to call the webhook (has `WEBHOOK_URL` and `WEBHOOK_SECRET`), and
     - Accepts requests from the Salesforce UI (e.g. Apex → your API, or Apex → AWS Lambda URL).
   - Flow: User clicks “Trigger ALB demo” in tab → Apex calls your API → API calls DevOps Agent webhook with a fixed ALB-unhealthy payload (like `trigger_alb_unhealthy_webhook.sh`).

2. **Case investigation**
   - “Investigate Case” button: Apex passes current Case Id to your API; API sends webhook payload with instructions to investigate and update that Case (same payload shape as `investigate_and_update_case.sh`). DevOps Agent must have Salesforce MCP connected (devops-service-api).

**Requirements:** Apex action, authenticated API (or Lambda URL), env with webhook URL/secret; DevOps Agent Space and webhook already set up.

---

### Option C: Hybrid (recommended for first step)

1. **Do Option A** in the DevOps Agent tab:
   - “Connect to Salesforce” subsection with steps from `devops-service-api` and `Salesforce-DevOps-Setup.md`.
   - “Run a demo” subsection with commands from `demo-trigger` and link to `README-ALARM-TRIGGER.md`.
2. **Later**, if you want in-UI triggers, add an Apex + API path (Option B) for “Trigger ALB demo” and “Investigate this Case.”

---

## 5. Suggested copy for the DevOps Agent tab (Option A)

**Section 1 – Connect DevOps Agent to Salesforce**

- “So DevOps Agent can read and update Salesforce Cases, register the Salesforce MCP Server with your DevOps Agent Space.”
- Steps (short): (1) Create Agent Space (`devops-service-api/create_devops_agent_space.sh`). (2) In Salesforce: enable MCP Beta, create External Client App with callback URL `https://api.prod.cp.aidevops.us-east-1.api.aws/v1/register/mcpserver/callback`. (3) Register and associate MCP (`register_salesforce_mcp.sh`, `associate_salesforce_mcp.sh`).
- Link: “Full setup: `devops-service-api/Salesforce-DevOps-Setup.md`.”

**Section 2 – Run a demo investigation**

- “Trigger an ALB unhealthy investigation (CloudWatch → SNS → Lambda → DevOps Agent): run `./demo-trigger/trigger_alb_unhealthy_alarm.sh`.”
- “Investigate a Case and add a comment: run `./demo-trigger/investigate_and_update_case.sh <CaseNumber>`. Requires webhook and Salesforce MCP configured.”
- Link: “Details: `demo-trigger/README-ALARM-TRIGGER.md`.”

This gives a clear path to enable both **devops-service-api** (connect Salesforce to DevOps Agent) and **demo-trigger** (run demos) from the DevOps Agent tab on the Salesforce UI, with the option to add UI-triggered demos later via a small backend.
