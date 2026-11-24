"""Token and cost accounting, plus the budget checks used by the HTTP middleware."""

from .config import (
    BUDGET_HARD_LIMIT_USD,
    PRICE_IN_PER_MTOK,
    PRICE_OUT_PER_MTOK,
    USER_DAILY_TOKEN_CAP,
)
from .db import get_pool

# claude-haiku-5-5 charges 5x for requests whose prompt is over 100K tokens.
LONG_PROMPT_TOKENS = 100_000
LONG_PROMPT_MULTIPLIER = 5


def estimate_cost(tokens_in: int, tokens_out: int) -> float:
    multiplier = LONG_PROMPT_MULTIPLIER if tokens_in > LONG_PROMPT_TOKENS else 1
    return multiplier * (tokens_in * PRICE_IN_PER_MTOK + tokens_out * PRICE_OUT_PER_MTOK) / 1_000_000


def record_usage(user_id: str, thread_id: str | None, tokens_in: int, tokens_out: int) -> float:
    """Log one chat turn and return its estimated cost in USD."""
    cost = estimate_cost(tokens_in, tokens_out)
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO usage_log (user_id, thread_id, tokens_in, tokens_out, cost_usd)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, thread_id, tokens_in, tokens_out, cost),
        )
    return cost


def check_budget(user_id: str) -> str | None:
    """Return why this request must be refused, or None if it may proceed.

    "global_budget"  -> estimated total spend reached BUDGET_HARD_LIMIT_USD
    "user_daily_cap" -> this user used USER_DAILY_TOKEN_CAP tokens today (UTC)
    """
    with get_pool().connection() as conn:
        spent = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS spent FROM usage_log").fetchone()["spent"]
        if float(spent) >= BUDGET_HARD_LIMIT_USD:
            return "global_budget"
        today = conn.execute(
            """
            SELECT COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens FROM usage_log
            WHERE user_id = %s AND created_at >= date_trunc('day', now())
            """,
            (user_id,),
        ).fetchone()["tokens"]
        if int(today) >= USER_DAILY_TOKEN_CAP:
            return "user_daily_cap"
    return None


def spend_summary() -> dict:
    """Totals for the admin dashboard."""
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0) AS spent, COALESCE(SUM(tokens_in), 0) AS tokens_in,
                   COALESCE(SUM(tokens_out), 0) AS tokens_out, count(*) AS chats
            FROM usage_log
            """
        ).fetchone()
    return {
        "spent_usd": round(float(row["spent"]), 6),
        "limit_usd": BUDGET_HARD_LIMIT_USD,
        "tokens_in": int(row["tokens_in"]),
        "tokens_out": int(row["tokens_out"]),
        "chats": int(row["chats"]),
    }
