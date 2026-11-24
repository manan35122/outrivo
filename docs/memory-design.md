# Memory design

## Short-term memory (per conversation)

- **Contains:** the messages, tool calls and tool results of one conversation, and any pending "send these?" question.
- **Key:** `thread_id`, stored as `"<len(user_id)>:<user_id>:<thread_id>"` so it is unique per user.
- **Stored in:** the LangGraph Postgres checkpointer (Neon), so it survives restarts and redeploys.
- **Trimming** (applies to the model input only; the full thread stays in the database):
  1. keep the last 12 messages, starting on a user message, and always the whole current turn;
  2. drop the oldest turns while the estimate is above about 4,000 tokens;
  3. shrink tool results from earlier turns to `id, company, name, city, stage`;
  4. add a one-line digest of what was dropped (built in code, no extra model call);
  5. if ids are needed that were dropped, the agent calls `get_pipeline`.

## Long-term memory (per user)

- **Contains:** durable facts about the user's own business. Allowed keys only:
  `name, business, offer, target_market, location, tone, preferences, goals`.
- **Key:** `user_id`. Table `user_memories`, `UNIQUE (user_id, key)`, so a new value updates the old one.
- **Read:** loaded at every model call and placed in the system prompt, labelled as data, not instructions.
- **Written:** by the `memory` node after the reply, only when the user's message talks about themselves.
  A small model call returns JSON; `memory.parse_facts` then enforces the rules below in code.
- **Never saved:** passwords, API keys, tokens, card or payment details, ID numbers, emails and phone
  numbers, lead contact details (they live in `leads`), full transcripts, small talk, anything from a
  blocked message, anything about other users. Values are capped at 200 characters and 20 keys per user.

## How users are kept separate

- Every table has a `user_id` column and every query filters by it.
- Tools get `user_id` from the server's request config, never from model output, so the model cannot be
  tricked into reading another user's data. A test checks that the tool schemas sent to the model contain
  no `user_id`.
- Conversations are stored under a key that includes `user_id`. Two users sending the same `thread_id`
  get separate conversations.
- The Guard refuses requests for other users' data before any model call.
- Long-term memory is loaded by `user_id` only, so one user's facts never appear in another's prompt (tested).
