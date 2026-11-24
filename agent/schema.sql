-- Run once in the Supabase / Neon SQL editor. Safe to re-run.
-- The LangGraph checkpointer creates its own tables (call checkpointer.setup()).

-- Long-term memory: durable facts per user
CREATE TABLE IF NOT EXISTS user_memories (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,          -- e.g. 'business', 'target_market', 'tone'
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories (user_id);

-- Note: there is no threads table. Conversations are stored by the LangGraph checkpointer under
-- "<len(user_id)>:<user_id>:<thread_id>", so a thread can never be shared between users.
-- (An older version of this file created an unused "threads" table; it is safe to drop.)

-- Leads found for a user
CREATE TABLE IF NOT EXISTS leads (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    company     TEXT,
    industry    TEXT,
    city        TEXT,
    email       TEXT,
    phone       TEXT,
    source      TEXT,
    stage       TEXT NOT NULL DEFAULT 'new',   -- new, contacted, replied, meeting, won, lost
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, email)                    -- searching twice never duplicates a lead
);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads (user_id);

-- Drafted / sent outreach messages
CREATE TABLE IF NOT EXISTS outreach (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    lead_id     BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL DEFAULT 'email',
    subject     TEXT,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',  -- draft, sent
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outreach_user ON outreach (user_id);
CREATE INDEX IF NOT EXISTS idx_outreach_lead ON outreach (lead_id);

-- Token and cost log, one row per chat turn (budget guard + admin usage page)
CREATE TABLE IF NOT EXISTS usage_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    thread_id   TEXT,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    NUMERIC(12, 6) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_user_time ON usage_log (user_id, created_at);

-- Risky actions waiting for the user's confirmation (two-turn gate)
CREATE TABLE IF NOT EXISTS pending_actions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    action      TEXT NOT NULL,                  -- e.g. 'send_outreach'
    payload     TEXT NOT NULL,                  -- JSON of the exact ids to act on
    request_id  TEXT,                           -- the /chat request that asked for confirmation
    status      TEXT NOT NULL DEFAULT 'pending',-- pending, done
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pending_user ON pending_actions (user_id, action, status);
