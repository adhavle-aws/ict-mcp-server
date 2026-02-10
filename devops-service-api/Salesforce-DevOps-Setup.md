Setup: Connecting AWS DevOps Agent to
Salesforce MCP Server
Blog Intake: ﻿ https://taskei.amazon.dev/tasks/ML-20390﻿ or ﻿ https://issues.amazon.com/issues/ML-20390﻿
Style Guide: ﻿ https://w.amazon.com/bin/view/ProductKnowledge/TechnicalWriting/Resources/StyleGuide/﻿
Service Names: ﻿ https://w.amazon.com/bin/view/AWSDocs/service-names/﻿
This document builds on the instruction in this Salesforce GitHub repo, describing the steps to setup and configure the
Salesforce MCP Server, and connect it to popular MCP Clients: PostMan, ChatGPT, Claude and Cursor.
﻿ https://github.com/forcedotcom/mcp-hosted?tab=readme-ov-file﻿
This documents adds the instructions for connecting the ﻿ Salesforce MCP Server﻿ to the ﻿ AWS DevOps Agent﻿ MCP Client.
The Salesforce documentation has five steps. The document will add instructions to step 2 and 4.
1.
2.
3.
4.
5.
Enable the Beta: turn on the opt-in setting that enables the MCP functionality in your org.
Create an External Client App: this prepares the target org to accept API requests from your MCP client.
Log Into Y our Target Org: to help the MCP client authenticate against your target org successfully , it’s best to log out of
all other orgs and log into the target org—before you attempt to configure and connect your MCP client.
Configure Y our MCP Client: with the org ready , you’ll configure the MCP client and connect it to the org in question.
Test Y our MCP Client: try the client’s chatbot capabilities to interact with your org in natural language.
Note: In this Beta release phase, the Salesforce MCP Server is only available in Sandbox Salesforce accounts.
MODIFIED STEP 2: CREA TE AN EXTERNAL CLIENT APP
In Step 2, we will create a Salesforce External Client App, to register and enable the DevOps Agent to integrate with
your Salesforce org using APIs and security controls.
When enabling OAuth Settings, this is the Callback URL: ﻿ https://api.prod.cp.aidevops.us-east-
1.api.aws/v1/register/mcpserver/callback﻿
As noted in the Salesforce documentation, the External Client App may need up to 30 minutes to become available and
operational worldwide.
MODIFIED STEP 4: CONFIGURE YOUR MCP CLIENT
The DevOps Agent must be configured to authenticate with the Salesforce hosted MCP server using OAuth 2.0 with
PKCE (Proof Key for Code Exchange), using the Three-Legged OAuth (3LO) method.
When creating the MCP Server, use this endpoint URL to connect to your Salesforce Sandbox.
﻿ https://api.salesforce.com/platform/mcp/v1-beta.2/sandbox/sobject-all﻿
-- screen shot here of creatung an MCP Server endpoint --
Click next.
Choose the 3LO Method, click next.
-- screen shot here showing selection of 3LO --
Complete the oAuth configuration:
Use the client ID and secret you obtained from step 1.
Exchange URL: ﻿ https://test.salesforce.com/services/oauth2/token﻿
Auth URL: ﻿ https://test.salesforce.com/services/oauth2/authorize﻿
Add scopes for: api sfap_
api refresh
token einstein
_
_gpt
_
api (Salesforce recommended scopes)
Additional Scope: offline
_
access (for Token Refresh)
PKCE must be selected
-- screen shot here showing authorization setup --
Click Next - you will be prompted to authenticate with
your Salesforce sandbox account.
-- screen shot here showinglogin to Salesforce --
After successful login, you can select the MCP Tools
to be available to the DevOps Agent.
-- screen shot here showing selection of MCP Tools --