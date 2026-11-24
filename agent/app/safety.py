"""Guard rules: prompt injection, requests for other users' data, off-topic, secret redaction.

Layers (cheapest first, so most abuse is stopped before any model spend):
  1. regex rules for injection and cross-user requests      (free)
  2. keyword / greeting allow-list for obviously on-topic   (free)
  3. a tiny model classifier (ON / OFF) for everything else (about 0.00003 USD)
The agent's own system prompt is a fourth layer, and the database layer
(user_id from the server, every query filtered) is the one that never depends on a model.
"""

import re

from .config import ANTHROPIC_API_KEY

# Planted in the system prompt. If a reply ever contains it, the prompt is leaking.
PROMPT_CANARY = "OUTRIVO-INTERNAL-7F3A91"

_I = re.IGNORECASE

INJECTION_PATTERNS = [
    re.compile(p, _I)
    for p in [
        r"\b(ignore|disregard|forget|override|bypass|skip|drop)\b.{0,40}\b(previous|prior|above|earlier|preceding|all|any|your|the|these|those|safety|system)\b.{0,30}\b(instructions?|rules?|prompts?|guidelines?|restrictions?|polic(y|ies)|programming|safeguards?|guardrails?)\b",
        r"\b(system|developer|hidden|initial|original|internal|secret)\s+(prompt|message|instructions?)\b",
        r"\b(reveal|show|print|repeat|output|display|leak|tell me|give me|share|dump|expose)\b.{0,30}\b(your|the)\b.{0,20}\b(prompt|instructions?|rules|configuration|config|api[ _-]?key|secret|password|token|credentials?)\b",
        r"\bapi[ _-]?keys?\b",
        r"\b(environment variables?|\.env\b|database[_ ]url|connection string|service[_ ]role)",
        r"\b(jailbreak|developer mode|dan mode|do anything now)\b",
        r"\byou are now\b",
        r"\bpretend (to be|you are|you're|that you)\b",
        r"\b(from now on|henceforth)\b.{0,20}\b(you|ignore|act|respond|answer)\b",
        r"</?\s*(system|assistant|instructions?)\s*>",
        r"\[/?\s*(system|inst)\s*\]",
        r"\bnew instructions?\s*:",
        r"\brepeat (everything|all|the text|the words) (above|before)\b",
    ]
]

OTHER_USER_PATTERNS = [
    re.compile(p, _I)
    for p in [
        r"\b(other|another|different|someone else'?s?|somebody else'?s?|every|all|any)\s+(users?'?s?|customers?'?s?|clients?'?s?|accounts?|people'?s?|persons?'?s?|businesses|tenants?)\b.{0,30}\b(data|leads?|pipeline|memor(y|ies)|conversations?|chats?|messages?|drafts?|info|information|history|details)",
        r"\b[\w-]+_[\w-]+'s\s+(data|leads?|pipeline|memor\w*|conversations?|chats?|drafts?|history)",
        r"\b(switch|impersonate|log ?in|login)\b.{0,20}\b(as|to)\b.{0,15}\b(user|account|admin)\b",
        r"\b(as|for) user[_ -]?\w+",
        r"\buser[_ ]?id\s*(=|:|is)\s*\S+",
        r"\bthread[_ ]?id\s*(=|:|is)\s*\S+",
    ]
]

GREETING = re.compile(
    r"^\W*(hi|hello|hey|hola|salam|assalam\w*|good (morning|afternoon|evening)|thanks?|thank you|"
    r"ok(ay)?|yes|yeah|yep|yup|no|nope|sure|confirm(ed)?|go ahead|please do|do it|cancel|stop)"
    r"(\s+(there|team|outrivo|everyone|please|thanks|thank you))?\W*$",
    _I,
)

ON_TOPIC = re.compile(
    r"\b(leads?|prospects?|outreach|pipeline|sales|sell(ing)?|customers?|clients?|business(es)?|"
    r"compan(y|ies)|agency|clinic|startup|marketing|campaign|follow[- ]?ups?|e-?mails?|whatsapp|"
    r"linkedin|drafts?|contacts?|replied|meetings?|pitch|industry|solar|dental|dentists?|real estate|"
    r"gyms?|fitness|boutique|software|coaching|tuition|lahore|karachi|islamabad|rawalpindi|faisalabad|"
    r"remember|my (name|tone|preferences?|services?|products?|offer))\b",
    _I,
)

SECRET_IN_TEXT = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|"
    r"postgres(ql)?://\S+:\S+@\S+|"
    r"\b(password|passcode|passwd|pwd|api[ _-]?key|secret|token|cvv|cvc|iban|otp)\b\s*(is|=|:)\s*\S+|"
    r"\b(?:\d[ -]?){13,19}\b)",
    _I,
)

REFUSAL_OFF_TOPIC = (
    "I'm Outrivo, a sales and outreach assistant. I can help you find leads, write outreach "
    "messages, and track your pipeline. What would you like to do?"
)
REFUSAL_INJECTION = (
    "I can't help with that. I can't share my instructions, keys or settings, and I can't change my rules. "
    "I'm happy to help with leads, outreach, or your pipeline."
)
REFUSAL_OTHER_USER = (
    "I can only access your own leads, drafts and memory, never another user's. "
    "Want me to show your own pipeline instead?"
)
REMOVED_MESSAGE = "[message removed by safety filter]"

CLASSIFIER_PROMPT = (
    "You are a topic filter for a sales assistant that finds leads, writes outreach messages "
    "(email, WhatsApp, LinkedIn), tracks a sales pipeline, and remembers the user's business details. "
    "Answer with exactly one word. ON if the message is about that work, about the user's own business, "
    "or is a short reply, greeting or confirmation. OFF for anything else (general knowledge, poems, "
    "stories, coding, homework, news, medical or legal advice, jokes, math, and so on)."
)


def looks_like_injection(message: str) -> bool:
    return any(p.search(message) for p in INJECTION_PATTERNS)


def asks_for_other_users_data(message: str) -> bool:
    return any(p.search(message) for p in OTHER_USER_PATTERNS)


def is_obviously_on_topic(message: str, has_history: bool) -> bool:
    """True when no classifier call is needed."""
    if GREETING.match(message) or ON_TOPIC.search(message):
        return True
    # a very short follow-up inside an ongoing conversation ("the first one", "make it shorter").
    # Anything longer goes to the classifier, so a poem request cannot slip in mid-conversation.
    return has_history and len(message.split()) <= 4


def is_risky_action(tool_name: str) -> bool:
    return tool_name in {"send_outreach"}


def contains_secret(text: str) -> bool:
    return bool(SECRET_IN_TEXT.search(text))


def redact(text: str) -> tuple[str, bool]:
    """Remove anything that looks like a key or connection string from a reply.
    Returns (clean_text, changed). A leaked system prompt is replaced by a refusal."""
    if PROMPT_CANARY in text:
        return REFUSAL_INJECTION, True
    changed = False
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY in text:
        text, changed = text.replace(ANTHROPIC_API_KEY, "[redacted]"), True
    cleaned = re.sub(r"sk-ant-[A-Za-z0-9_-]{8,}|postgres(ql)?://\S+", "[redacted]", text)
    return cleaned, changed or cleaned != text
