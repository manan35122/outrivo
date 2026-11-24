# Architecture

## Request path

```
Browser / grader
  -> CORSMiddleware
  -> RequestContextMiddleware   request id, timing, access log, last-resort error catch
  -> ChatGuardMiddleware        validate body, rate limit, budget guard   (POST /chat only)
  -> FastAPI route /chat        chat_service.run_chat
  -> LangGraph: guard -> agent <-> tools -> memory
  -> Postgres (Neon / Supabase)
```

## Graph (LangGraph)

```
START -> guard --(blocked)--> END
           |
           +--(allowed)--> agent --(tool calls)--> tools --> agent
                              |
                              +--(final answer)--> memory --> END
```

| Node | Job |
|---|---|
| `guard` | Blocks prompt injection, requests for other users' data, and off-topic messages. Rules first, a 5-token classifier call only when unclear. Replaces a blocked message in the stored thread. |
| `agent` | claude-haiku-5-5 with the 5 tools bound. Receives the system prompt, the user's long-term memories, and the trimmed thread. |
| `tools` | Runs `search_leads`, `draft_outreach`, `update_pipeline`, `get_pipeline`, `send_outreach` one at a time. Bad arguments return an error to the model. |
| `memory` | Extracts business facts from the user's message and saves them per `user_id`. Best effort: a failure never loses the reply. |

## One chat turn

1. `POST /chat` receives `user_id`, `thread_id`, `message`.
2. Middleware validates the body, applies rate limits and checks the budget.
3. `run_chat` starts the graph with config `{thread_id: namespaced key, user_id, request_id}` and a callback collector.
4. The Guard decides allow or block.
5. The agent loads the user's memories, trims the thread, calls the model. Tool calls loop through `tools` until the model gives a final answer, up to 8 tool calls per turn.
6. The memory node saves any new business facts.
7. The reply is scrubbed for keys and the prompt canary, usage is logged, and the response returns `reply`, `tool_calls` (name, args, result) and `tokens` (summed over every model call in the turn).

## Where the safety checks live

| Risk | Check | Where |
|---|---|---|
| Malformed or huge input | Body validation, size limits | `ChatGuardMiddleware` |
| Spam on the open endpoint | Rate limit per IP and per user | `ChatGuardMiddleware` |
| Budget overrun | Estimated spend and per-user daily token cap | `ChatGuardMiddleware` + `usage.py` |
| Prompt injection, off-topic | Rules, then classifier, then system prompt | `guard` node, `safety.py`, `prompts.py` |
| One user reading another's data | `user_id` from config, every query filtered, namespaced threads | `tools.py`, `memory.py`, `chat_service.py` |
| Accidental mass send | Two-request confirmation gate | `send_outreach` in `tools.py` |
| Runaway tool loop | 8 tool calls per turn, recursion limit 30 | `graph.py`, `chat_service.py` |
| Tool crash | `safe_tool` returns a readable error | `tools.py` |
| Secrets in memory or replies | Filtered before saving, scrubbed before returning | `memory.py`, `safety.py` |
| Unexpected server error | Friendly chat-shaped reply, never a 500 on `/chat` | `RequestContextMiddleware`, `run_chat` |

## Cost control

- Official price for `claude-haiku-5-5`: $0.10 in / $0.50 out per million tokens for prompts up to 100K tokens, and 5x above that. History trimming keeps every request far below 100K tokens.
- Guard rules run before any model call. The classifier answers in at most 5 tokens, the memory extractor in at most 300, and only when the user talked about themselves.
- The budget guard stops new requests at `BUDGET_HARD_LIMIT_USD`, below the key's $2 limit.
