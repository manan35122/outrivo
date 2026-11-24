# Outrivo

AI sales and outreach engine: finds leads, writes personalised outreach, and tracks the pipeline. Built for the **Design to Production: Agentic AI Hackathon** (Track 05, GrowthPilot).

- **Live website:** _TODO (Vercel URL)_
- **Agent API base URL:** https://outrivo.onrender.com
- **Demo video:** _TODO_

## Build progress

- [x] Project skeleton, schema, docs
- [x] **Tools:** 5 tools, demo lead dataset, Postgres layer
- [x] **Middleware:** request context, validation, rate limit, budget guard, usage tracking
- [x] **LangGraph agent:** Guard, Outreach Agent, Tool Executor, Memory Agent; short-term memory (Postgres checkpointer), long-term memory (per user), history trimming, `/chat` wired (123 tests)
- [ ] Verified against the real Claude API (run `python -m app.selfcheck`, see Setup)
- [ ] Website: customer page and admin dashboard
- [ ] Deploy: API on Hugging Face Spaces / Render, website on Vercel
- [ ] Benchmark numbers, demo GIF, demo video

## What it does

| Capability | How |
|---|---|
| Find leads | `search_leads` finds prospects for a target market and saves them to the user's pipeline |
| Write outreach | The agent writes a personalised message, `draft_outreach` saves it as a draft |
| Track pipeline | `update_pipeline` / `get_pipeline` move leads through new, contacted, replied, meeting, won, lost |
| Ask before risky actions | `send_outreach` needs the user's confirmation, enforced on the server |
| Remember users | Short-term memory per `thread_id`, long-term memory per `user_id` |

## Architecture

```mermaid
flowchart TD
    C[Customer page / Admin dashboard<br/>Next.js on Vercel] --> MW
    B[Hidden benchmark] --> MW
    MW[HTTP middleware<br/>validate, rate limit, budget guard] --> API[FastAPI<br/>POST /chat, GET /health]
    API --> G[Guard Agent]
    G -->|blocked: injection, other user's data, off-topic| R[Refusal reply]
    G -->|allowed| A[Outreach Agent<br/>claude-haiku-5-5]
    A -->|tool calls| T[Tool Executor<br/>5 tools]
    T -->|results| A
    A -->|final answer| M[Memory Agent<br/>saves business facts]
    M --> OUT[reply + tool_calls + tokens]
    T <--> DB[(Postgres<br/>Neon / Supabase)]
    M <--> DB
    A <-->|checkpointer: thread memory| DB
```

| Node | Job |
|---|---|
| **Guard Agent** (`guard`) | Regex rules for prompt injection and requests for other users' data (free). Then a keyword shortcut for obviously on-topic messages. Only unclear messages go to a tiny ON/OFF model call (5 output tokens). Blocked messages are removed from the stored thread. |
| **Outreach Agent** (`agent`) | The main model. Gets the system prompt, the user's long-term memories, and the trimmed thread; decides which tools to call and writes the reply. |
| **Tool Executor** (`tools`) | Runs the model's tool calls one at a time, passing `user_id` from the server config. Bad arguments come back as an error the model can fix. |
| **Memory Agent** (`memory`) | After the reply, when the user said something about themselves, a small model call extracts business facts and saves them per `user_id`. |

Per turn the agent can use at most **8 tool calls** (the demo needs 4: one search and three drafts). A step past the limit is replaced by a short "step limit" reply, so no half-finished tool call is ever stored. Details in [docs/architecture.md](docs/architecture.md).

## Tools

| Tool | What it does | Risk |
|---|---|---|
| `search_leads(query, limit)` | Finds prospects by industry and/or city, saves them as `new` leads (max 5) | none |
| `draft_outreach(lead_id, subject, body, channel)` | Saves a message the agent wrote as a **draft**. Redrafting replaces the old draft | none |
| `update_pipeline(lead_id, stage)` | Moves a lead to a stage | low |
| `get_pipeline(stage?)` | Counts per stage plus recent leads, with their draft ids | none |
| `send_outreach(outreach_ids)` | Sends drafts after confirmation (max 10) | **risky** |

How the tools stay safe:

- **The model never chooses `user_id`.** It is read from the request config set by the server, so the tool schemas the model sees contain no `user_id`. Every SQL statement filters by it. A test checks the exact request the real Claude client sends.
- **Confirmation gate for `send_outreach`.** The first call records a pending action and sends nothing. It only sends when the same ids are requested again in a **later** `/chat` request (a different `request_id`), meaning the user answered. The model cannot confirm its own question, even if a prompt injection tells it to. If request ids are missing, it never sends.
- **`safe_tool` wrapper.** Any error becomes `{"error": "..."}` that the model can explain, so a tool failure never crashes the graph or becomes a 500.
- **Demo data.** `search_leads` searches 32 fictional businesses in `agent/app/data/demo_leads.json` (8 industries, 5 cities). It is fast, free and repeatable, which keeps benchmark runs reliable and cheap. Searching twice never duplicates a lead.
- **Sending is simulated** (`SEND_MODE=simulate`): messages are recorded as sent and the agent says so. No real email leaves the system.

## Memory design

**Short-term memory (one conversation)**
- Holds the messages, tool calls and tool results of one `thread_id`, including a pending "send these?" question.
- Stored by the LangGraph **Postgres checkpointer** in Neon, so it survives server restarts and redeploys (tested).
- The thread is stored under `"<len(user_id)>:<user_id>:<thread_id>"`. Two users who send the same `thread_id` get two separate conversations, and one can never read the other's.
- **Trimming long chats** (only what is sent to the model; the full thread stays stored): keep the last 12 messages starting on a user message, always keep the whole current turn, drop oldest turns while above about 4,000 tokens, shrink tool results from earlier turns to `id, company, name, city, stage`, and add a one-line digest of what was dropped (built in code, no extra model call). If the agent needs ids that were dropped, it calls `get_pipeline`.

**Long-term memory (across conversations)**
- Stored in the `user_memories` table, one row per `(user_id, key)`. Loaded into the agent's prompt at every model call.
- **Saved:** only these keys: `name, business, offer, target_market, location, tone, preferences, goals`. Values are short (max 200 characters), at most 20 keys per user.
- **Not saved:** passwords, API keys, tokens, card or payment details, ID numbers, emails and phone numbers, lead contact details (those live in the `leads` table), full transcripts, small talk, anything from a blocked message, and anything about other users. This is enforced in code (`memory.parse_facts`), not just by prompt.

**How users are kept separate**
- Every table has a `user_id` column and every query filters on it.
- Tools get `user_id` from the server, never from model output.
- Threads are namespaced by `user_id` (above), so conversation history cannot cross users either.
- The Guard refuses requests for other users' data before any model call, and the database layer makes it impossible even if the Guard missed.

## Safety

| Risk | Defence |
|---|---|
| Prompt injection | Regex rules in the Guard run first, and the system prompt tells the model that user text, lead notes and tool results are data, not commands |
| Off-topic requests | Keyword shortcut, then a tiny ON/OFF classifier, then the system prompt as a backstop |
| Other users' data | Guard rule, `user_id` from the server, every query filtered, threads namespaced |
| Risky actions | Server-side confirmation gate on `send_outreach` |
| Leaking the prompt or keys | A canary token in the system prompt, and secrets and connection strings are scrubbed from every reply |
| Leaked key in memory | Secrets and contact details are filtered before anything is saved |

## Middleware: where it is used

Middleware means code that wraps every request or tool call, so the checks live in one place and cannot be forgotten.

| Layer | Middleware | What it does |
|---|---|---|
| **HTTP** (`middleware.py`) | `RequestContextMiddleware` | Gives each request an `X-Request-ID` and timing, logs it, and catches unexpected errors. On `/chat` an error becomes a friendly reply in the normal chat shape, never a 500 |
| **HTTP** | `ChatGuardMiddleware` | `POST /chat` only. Rejects bad or oversized bodies (422 / 413), rate limits per IP and per `user_id` (429 + `Retry-After`), then runs the budget guard |
| **HTTP** | `CORSMiddleware` | Lets the Vercel website call the API from the browser |
| **Tools** (`tools.py`) | `safe_tool` + user injection | Reads `user_id` from the server config, turns any tool failure into a readable error |
| **Tools** | Confirmation gate | `send_outreach` only sends in a later request than the one that asked |
| **Graph** (`graph.py`, `history.py`) | Per-turn limits and trimming | Caps tool calls per turn, trims history before each model call |

Request path: `CORS -> RequestContext -> ChatGuard -> FastAPI route -> graph -> tools`.

**Budget guard.** Each chat turn is logged to `usage_log` with its estimated cost, using the official `claude-haiku-5-5` price ([pricing](https://platform.claude.com/docs/en/about-claude/pricing): $0.10 in / $0.50 out per million tokens, 5x for prompts over 100K tokens). The guard refuses politely when total estimated spend reaches `BUDGET_HARD_LIMIT_USD` (default $1.60, below the key's $2 limit) or one user passes `USER_DAILY_TOKEN_CAP` tokens in a day. If the budget check itself fails, the request is let through, so an outage does not take the agent down.

**Limits (configurable in `.env`):** 30 requests/min per user, 300/min per IP, 2,000 characters per message, 16 KB per body.

## Repo layout

```
outrivo/
├── README.md
├── .env.example
├── tests.json                # our own 10 benchmark cases (machine-checkable)
├── scripts/run_benchmark.py  # runs tests.json against a live API, prints the results table
├── agent/                    # LangGraph agent + FastAPI (deploy to HF Spaces / Render)
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   ├── schema.sql            # Postgres tables
│   ├── tests/                # pytest suite (123 tests)
│   └── app/
│       ├── main.py           # /chat and /health, wires the middleware
│       ├── middleware.py     # request context, validation, rate limit, budget guard
│       ├── chat_service.py   # builds the graph, runs one turn, shapes the response
│       ├── graph.py          # the LangGraph: guard, agent, tools, memory
│       ├── prompts.py        # system prompt, classifier and extractor prompts
│       ├── safety.py         # Guard rules and secret redaction
│       ├── history.py        # short-term memory trimming
│       ├── memory.py         # long-term memory and fact filtering
│       ├── tools.py          # the 5 tools
│       ├── callbacks.py      # collects tokens and tool calls per request
│       ├── usage.py          # token and cost log, budget checks
│       ├── selfcheck.py      # python -m app.selfcheck
│       ├── db.py, config.py
│       └── data/demo_leads.json
├── web/                      # customer page + admin dashboard (deploy to Vercel)
└── docs/
```

## Setup

1. **Clone and configure**
   ```bash
   git clone <repo-url> && cd outrivo
   cp .env.example .env      # fill in values. Never commit .env
   ```
2. **Database:** create a free Neon (or Supabase) project, put the **pooled** connection string in `DATABASE_URL`, then run `agent/schema.sql` in its SQL editor.
3. **Install and verify**
   ```bash
   cd agent
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   python -m app.selfcheck   # reads the .env in the repo root; checks env, database, your Claude key, and one real chat (costs < 1 cent)
   ```
4. **Run the API**
   ```bash
   uvicorn app.main:app --reload --port 8000
   curl localhost:8000/health
   curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
     -d '{"user_id":"u1","thread_id":"t1","message":"Find me 3 dental clinics in Lahore"}'
   ```
5. **Deploy:** agent to Hugging Face Spaces (Docker) or Render, website to Vercel. Set the same env vars in each dashboard.

## Tests

The DB tests need a **throwaway** Postgres database. The tests wipe its tables, so the name must contain `test` or the run refuses to start.

```bash
cd agent
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/outrivo_test python -m pytest -q
```

Without `TEST_DATABASE_URL`, DB tests are skipped. With it, all 123 run. The model is replaced by a scripted fake in most tests, and two tests run the **real** `ChatAnthropic` client against a local fake of the Anthropic API to check the exact requests we send (tool schemas, tool results, token counts). Tests cannot prove how the real model behaves: that is what `selfcheck` and the benchmark are for.

## Benchmark

Run our 10 cases against the live API:

```bash
pip install httpx
python scripts/run_benchmark.py https://YOUR-API-URL            # one run, shows each check
python scripts/run_benchmark.py https://YOUR-API-URL --repeat 3  # consistency over 3 runs
```

_TODO: paste the table it prints here after the live run._

| Metric | Result |
|---|---|
| Test cases passed | _/10_ |
| Median latency | _s_ |
| Avg tokens in / out per chat | _ / _ |
| Avg cost per chat | _$_ |

## Agent API

`POST /chat` with `{"user_id": "u1", "thread_id": "t1", "message": "..."}` returns
`{"reply": "...", "tool_calls": [{"name": "...", "args": {...}, "result": {...}}], "tokens": {"in": 0, "out": 0}}`

`GET /health` returns `ok`. Both are open (no login), as required for grading.

Even errors keep the chat shape (`reply`, `tool_calls`, `tokens`, plus an `error` field): `422` invalid body, `413` too large, `429` rate limited, `200` with `error: "agent_error"` if the model is down, and `200` with `blocked` set when the budget guard refuses.

## Demo

_TODO: add demo GIF (`docs/demo.gif`)._

## Team

_TODO: group name and members._
