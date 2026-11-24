import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-haiku-5-5")
DATABASE_URL = os.getenv("DATABASE_URL", "")
# Must be large enough for a tool call that carries several drafted emails; a reply cut
# off mid tool call would be broken. At $0.50 per million output tokens this costs almost nothing.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1200"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# Agent limits per chat turn
MAX_TOOL_CALLS_PER_TURN = int(os.getenv("MAX_TOOL_CALLS_PER_TURN", "8"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "4000"))

# Optional. Left unset because some newer Claude models reject sampling parameters.
_temperature = os.getenv("TEMPERATURE", "").strip()
TEMPERATURE = float(_temperature) if _temperature else None

# "simulate": send_outreach records messages as sent but dispatches nothing real.
SEND_MODE = os.getenv("SEND_MODE", "simulate")

# Cost estimate for claude-haiku-5-5, USD per million tokens, for prompts up to 100K tokens.
# Prompts over 100K tokens cost 5x (see usage.py). Source:
# https://platform.claude.com/docs/en/about-claude/pricing
PRICE_IN_PER_MTOK = float(os.getenv("PRICE_IN_PER_MTOK", "0.10"))
PRICE_OUT_PER_MTOK = float(os.getenv("PRICE_OUT_PER_MTOK", "0.50"))

# Budget guards (the key itself has a hard $2 limit, so stop well before it).
BUDGET_HARD_LIMIT_USD = float(os.getenv("BUDGET_HARD_LIMIT_USD", "1.60"))
USER_DAILY_TOKEN_CAP = int(os.getenv("USER_DAILY_TOKEN_CAP", "200000"))

# Request limits enforced by the HTTP middleware.
RATE_LIMIT_USER_PER_MIN = int(os.getenv("RATE_LIMIT_USER_PER_MIN", "30"))
RATE_LIMIT_IP_PER_MIN = int(os.getenv("RATE_LIMIT_IP_PER_MIN", "300"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "2000"))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "16384"))
