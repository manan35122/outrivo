"""Long-term memory per user_id.

Every query MUST filter by user_id so users never see each other's data.
Only a short allow-list of business facts is ever stored (see ALLOWED_KEYS), and values that
look like secrets, card numbers or contact details are dropped before saving.
"""

import json
import re

from .db import get_pool
from .safety import contains_secret

ALLOWED_KEYS = ("name", "business", "offer", "target_market", "location", "tone", "preferences", "goals")
MAX_VALUE_CHARS = 200
MAX_KEYS_PER_USER = 20

_EMAIL_OR_PHONE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s().-]{8,}\d")


def load_memories(user_id: str) -> dict[str, str]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM user_memories WHERE user_id = %s", (user_id,)
        ).fetchall()
    return {r["key"]: r["value"] for r in rows}


def save_memory(user_id: str, key: str, value: str) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO user_memories (user_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (user_id, key, value),
        )


def parse_facts(raw: str) -> dict[str, str]:
    """Pull the first JSON object out of a model reply and keep only safe, allowed facts."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    facts: dict[str, str] = {}
    for key, value in data.items():
        key = str(key).strip().lower()
        if key not in ALLOWED_KEYS:
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if not isinstance(value, (str, int, float)):
            continue
        value = str(value).strip()
        if not value or contains_secret(value) or _EMAIL_OR_PHONE.search(value):
            continue
        facts[key] = value[:MAX_VALUE_CHARS]
    return facts


def save_facts(user_id: str, facts: dict[str, str]) -> int:
    """Save facts (keys are already validated). Returns how many were saved."""
    if not facts:
        return 0
    known = set(load_memories(user_id))
    saved = 0
    for key, value in facts.items():
        if key not in known and len(known) >= MAX_KEYS_PER_USER:
            continue
        save_memory(user_id, key, value)
        known.add(key)
        saved += 1
    return saved
