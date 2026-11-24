"""Outrivo agent tools.

Design rules:
- The model never supplies user_id. It comes from the request config
  (config["configurable"]["user_id"]), which the server sets in main.py.
  The tool schemas the model sees contain no user_id and no config.
- Every SQL statement filters by user_id.
- Tools never raise into the graph: safe_tool turns errors into {"error": "..."}
  that the model can read and explain.
- Risky actions (send_outreach) go through a server-side two-turn confirmation
  gate that the model cannot skip, even if a prompt injection tells it to.
"""

import functools
import json
import logging
import re
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from .config import SEND_MODE
from .db import get_pool

log = logging.getLogger("outrivo.tools")

STAGES = ("new", "contacted", "replied", "meeting", "won", "lost")
CHANNELS = ("email", "whatsapp", "linkedin")
MAX_SEARCH_LIMIT = 5
MAX_PIPELINE_ROWS = 30
MAX_SEND_BATCH = 10
CONFIRM_TTL_MINUTES = 15
MAX_SUBJECT_CHARS = 150
MAX_BODY_CHARS = 1500

# Demo dataset of fictional businesses. Searching it is free, fast and repeatable,
# which keeps the hidden benchmark reliable and the token cost low.
DEMO_LEADS: list[dict] = json.loads(
    (Path(__file__).parent / "data" / "demo_leads.json").read_text(encoding="utf-8")
)


class ToolError(Exception):
    """A problem the model can understand and explain to the user."""


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def _context(config: RunnableConfig | None) -> tuple[str, str | None]:
    """Read user_id and request_id from the server-controlled config."""
    cfg = (config or {}).get("configurable") or {}
    user_id = cfg.get("user_id")
    if not user_id or not isinstance(user_id, str):
        raise ToolError("No user in context.")
    return user_id, cfg.get("request_id")


def safe_tool(fn):
    """Tool-level middleware: convert every failure into a readable result."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError as e:
            return {"error": str(e)}
        except Exception:
            log.exception("tool %s failed", fn.__name__)
            return {"error": "The tool failed temporarily. Please try again."}

    return wrapper


# --------------------------------------------------------------------------
# Demo lead search index
# --------------------------------------------------------------------------

_STOPWORDS = {
    "find", "me", "leads", "lead", "for", "in", "a", "an", "the", "of", "and", "to",
    "get", "show", "some", "business", "businesses", "company", "companies",
    "prospect", "prospects", "near", "who", "need", "needs", "want", "please",
    "write", "outreach", "them", "each", "with", "my", "i", "give", "list",
    "search", "new", "few", "two", "three", "four", "five", "owner", "owners",
    "based", "local", "small", "any", "all", "on", "at", "from",
}


def _stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


_INDEX: list[tuple[dict, set[str]]] = [
    (
        lead,
        {_stem(w) for w in _words(f"{lead['company']} {lead['industry']} {' '.join(lead.get('keywords', []))}")},
    )
    for lead in DEMO_LEADS
]
KNOWN_CITIES = {lead["city"].lower() for lead in DEMO_LEADS}
INDUSTRIES = sorted({lead["industry"] for lead in DEMO_LEADS})


def _match_demo_leads(query: str, limit: int) -> list[dict]:
    words = _words(query)
    cities = {w for w in words if w in KNOWN_CITIES}
    terms = {_stem(w) for w in words if w not in KNOWN_CITIES and w not in _STOPWORDS}
    if not cities and not terms:
        raise ToolError(
            "Ask the user which industry and/or city to target. "
            f"Industries available: {', '.join(INDUSTRIES)}."
        )
    scored = []
    for lead, lead_terms in _INDEX:
        if cities and lead["city"].lower() not in cities:
            continue
        score = len(terms & lead_terms)
        if terms and score == 0:
            continue
        scored.append((score, lead))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    top = sorted((lead for score, lead in scored if score == best), key=lambda l: l["company"])
    return top[:limit]


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


@tool
@safe_tool
def search_leads(query: str, limit: int = 3, *, config: RunnableConfig) -> dict:
    """Find prospects for the user's target market, e.g. 'dental clinic Lahore' or 'solar installers'.
    Use industry and/or city words. Saves the leads to the user's pipeline (stage 'new') and
    returns each with a personalisation note. Returns at most 5 leads."""
    user_id, _ = _context(config)
    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    matches = _match_demo_leads(query, limit)
    if not matches:
        return {
            "count": 0,
            "leads": [],
            "hint": (
                f"No leads matched. Industries available: {', '.join(INDUSTRIES)}. "
                f"Cities available: {', '.join(sorted(c.title() for c in KNOWN_CITIES))}."
            ),
        }
    leads = []
    with get_pool().connection() as conn:
        for lead in matches:
            row = conn.execute(
                """
                INSERT INTO leads (user_id, name, company, industry, city, email, phone, source, notes)
                VALUES (%(user_id)s, %(name)s, %(company)s, %(industry)s, %(city)s,
                        %(email)s, %(phone)s, 'demo', %(notes)s)
                ON CONFLICT (user_id, email) DO UPDATE SET updated_at = now()
                RETURNING id, name, company, industry, city, email, phone, stage, notes
                """,
                {**lead, "user_id": user_id},
            ).fetchone()
            leads.append(row)
    return {"count": len(leads), "leads": leads}


@tool
@safe_tool
def draft_outreach(
    lead_id: int, subject: str, body: str, channel: str = "email", *, config: RunnableConfig
) -> dict:
    """Save a personalised outreach message as a DRAFT for one lead. This does NOT send anything.
    Write the subject and body yourself, using the lead's details and note and what you know about
    the user's business, then call this to save it. channel: email, whatsapp or linkedin.
    Drafting again for the same lead and channel replaces the earlier draft."""
    user_id, _ = _context(config)
    channel = (channel or "").lower().strip()
    if channel not in CHANNELS:
        raise ToolError(f"Channel must be one of: {', '.join(CHANNELS)}.")
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not body:
        raise ToolError("The message body is empty.")
    if channel == "email" and not subject:
        raise ToolError("An email needs a subject.")
    if len(subject) > MAX_SUBJECT_CHARS or len(body) > MAX_BODY_CHARS:
        raise ToolError(
            f"Too long: subject max {MAX_SUBJECT_CHARS} characters, body max {MAX_BODY_CHARS}."
        )
    with get_pool().connection() as conn:
        lead = conn.execute(
            "SELECT id, company FROM leads WHERE id = %s AND user_id = %s", (lead_id, user_id)
        ).fetchone()
        if not lead:
            raise ToolError("Lead not found.")
        with conn.transaction():
            conn.execute(
                "DELETE FROM outreach WHERE user_id = %s AND lead_id = %s AND channel = %s AND status = 'draft'",
                (user_id, lead_id, channel),
            )
            row = conn.execute(
                """
                INSERT INTO outreach (user_id, lead_id, channel, subject, body)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (user_id, lead_id, channel, subject or None, body),
            ).fetchone()
    return {
        "outreach_id": row["id"],
        "lead_id": lead_id,
        "company": lead["company"],
        "channel": channel,
        "status": "draft",
        "note": "Saved as a draft. Nothing has been sent.",
    }


@tool
@safe_tool
def update_pipeline(lead_id: int, stage: str, *, config: RunnableConfig) -> dict:
    """Move a lead to a pipeline stage: new, contacted, replied, meeting, won or lost."""
    user_id, _ = _context(config)
    stage = (stage or "").lower().strip()
    if stage not in STAGES:
        raise ToolError(f"Stage must be one of: {', '.join(STAGES)}.")
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            UPDATE leads SET stage = %s, updated_at = now()
            WHERE id = %s AND user_id = %s
            RETURNING id AS lead_id, company, name, stage
            """,
            (stage, lead_id, user_id),
        ).fetchone()
    if not row:
        raise ToolError("Lead not found.")
    return row


@tool
@safe_tool
def get_pipeline(stage: str | None = None, *, config: RunnableConfig) -> dict:
    """Show the user's pipeline: lead counts per stage and the most recent leads, with the ids of
    their unsent drafts (draft_ids) and how many messages were sent. Optionally filter by stage."""
    user_id, _ = _context(config)
    stage = (stage or "").lower().strip() or None
    if stage and stage not in STAGES:
        raise ToolError(f"Stage must be one of: {', '.join(STAGES)}.")
    with get_pool().connection() as conn:
        counts = conn.execute(
            "SELECT stage, count(*) AS n FROM leads WHERE user_id = %s GROUP BY stage", (user_id,)
        ).fetchall()
        leads = conn.execute(
            """
            SELECT l.id, l.company, l.name, l.city, l.stage,
                   ARRAY(SELECT o.id FROM outreach o
                         WHERE o.lead_id = l.id AND o.user_id = l.user_id AND o.status = 'draft'
                         ORDER BY o.id) AS draft_ids,
                   (SELECT count(*) FROM outreach o
                    WHERE o.lead_id = l.id AND o.user_id = l.user_id AND o.status = 'sent') AS sent
            FROM leads l
            WHERE l.user_id = %s AND (%s::text IS NULL OR l.stage = %s)
            ORDER BY l.updated_at DESC, l.id DESC
            LIMIT %s
            """,
            (user_id, stage, stage, MAX_PIPELINE_ROWS),
        ).fetchall()
    by_stage = {s: 0 for s in STAGES}
    by_stage.update({r["stage"]: r["n"] for r in counts})
    return {"total": sum(by_stage.values()), "by_stage": by_stage, "leads": leads}


@tool
@safe_tool
def send_outreach(outreach_ids: list[int], *, config: RunnableConfig) -> dict:
    """Send drafted messages. RISKY, so it needs the user's confirmation: the first call sends
    nothing and returns the recipients. Tell the user who will receive the messages and ask them
    to confirm. Only after they reply yes in a NEW message, call this again with the same
    outreach_ids. Sends at most 10 messages per call."""
    user_id, request_id = _context(config)
    try:
        ids = sorted({int(i) for i in outreach_ids})
    except (TypeError, ValueError):
        raise ToolError("outreach_ids must be a list of draft ids.")
    if not ids:
        raise ToolError("No messages selected.")
    if len(ids) > MAX_SEND_BATCH:
        raise ToolError(f"Send at most {MAX_SEND_BATCH} messages at a time.")
    if SEND_MODE != "simulate":
        raise ToolError("Real sending is not configured yet.")
    payload = json.dumps(ids)

    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT o.id, o.status, l.company
            FROM outreach o JOIN leads l ON l.id = o.lead_id AND l.user_id = o.user_id
            WHERE o.user_id = %s AND o.id = ANY(%s)
            ORDER BY o.id
            """,
            (user_id, ids),
        ).fetchall()
        if len(rows) != len(ids):
            raise ToolError("Some of those drafts were not found.")
        already_sent = [r["id"] for r in rows if r["status"] != "draft"]
        if already_sent:
            raise ToolError(f"Already sent: {already_sent}.")
        recipients = [r["company"] for r in rows]

        pending = conn.execute(
            """
            SELECT id, request_id FROM pending_actions
            WHERE user_id = %s AND action = 'send_outreach' AND payload = %s
              AND status = 'pending' AND created_at > now() - make_interval(mins => %s)
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, payload, CONFIRM_TTL_MINUTES),
        ).fetchone()

        # Confirmed only if the confirmation was requested in an EARLIER request
        # (a different /chat call) than this one. Fails closed if request ids are missing.
        confirmed = bool(
            pending
            and request_id
            and pending["request_id"]
            and pending["request_id"] != request_id
        )
        if not confirmed:
            if not pending:
                conn.execute(
                    "INSERT INTO pending_actions (user_id, action, payload, request_id) VALUES (%s, 'send_outreach', %s, %s)",
                    (user_id, payload, request_id),
                )
            return {
                "status": "confirmation_required",
                "sent": False,
                "count": len(rows),
                "recipients": recipients,
                "message": (
                    f"NOT SENT YET. Tell the user you are about to send {len(rows)} message(s) to: "
                    f"{', '.join(recipients)}. Ask them to confirm. Call send_outreach again with the "
                    "same ids only after they reply yes in a new message."
                ),
            }

        with conn.transaction():
            conn.execute(
                "UPDATE outreach SET status = 'sent', sent_at = now() WHERE user_id = %s AND id = ANY(%s)",
                (user_id, ids),
            )
            conn.execute(
                """
                UPDATE leads SET stage = 'contacted', updated_at = now()
                WHERE user_id = %s AND stage = 'new'
                  AND id IN (SELECT lead_id FROM outreach WHERE user_id = %s AND id = ANY(%s))
                """,
                (user_id, user_id, ids),
            )
            conn.execute("UPDATE pending_actions SET status = 'done' WHERE id = %s", (pending["id"],))

    log.info("SIMULATED SEND user=%s outreach_ids=%s", user_id, ids)
    return {
        "status": "sent",
        "sent": True,
        "mode": "simulated",
        "count": len(rows),
        "recipients": recipients,
        "note": "Demo mode: messages are recorded as sent; no real email or message left the system.",
    }


ALL_TOOLS = [search_leads, draft_outreach, update_pipeline, get_pipeline, send_outreach]
