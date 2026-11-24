"""Short-term memory trimming: what part of a long thread is sent to the model.

The full thread stays stored in Postgres (checkpointer). Only the model input is trimmed:
  1. keep the most recent MAX_HISTORY_MESSAGES messages, starting on a user message,
     and always keep the whole current turn;
  2. drop the oldest turns while the estimate is above MAX_HISTORY_TOKENS;
  3. shrink tool results from earlier turns to the useful fields (id, company, name, stage);
  4. describe what was dropped in a one-line digest (built in code, no extra model call).
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .config import MAX_HISTORY_MESSAGES, MAX_HISTORY_TOKENS

OLD_TOOL_RESULT_CHARS = 600
LEAD_FIELDS = ("id", "company", "name", "city", "stage")


def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def _estimate_tokens(messages) -> int:
    return sum(len(str(m.content)) for m in messages) // 4


def _compact_tool_message(message: ToolMessage) -> ToolMessage:
    raw = text_of(message)
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("leads"), list):
        data = {
            **{k: v for k, v in data.items() if k != "leads"},
            "leads": [{f: lead[f] for f in LEAD_FIELDS if f in lead} for lead in data["leads"] if isinstance(lead, dict)],
        }
        raw = json.dumps(data)
    if len(raw) > OLD_TOOL_RESULT_CHARS:
        raw = raw[:OLD_TOOL_RESULT_CHARS] + "...(shortened)"
    return ToolMessage(content=raw, tool_call_id=message.tool_call_id, name=message.name)


def _digest(dropped) -> str | None:
    if not dropped:
        return None
    said = [text_of(m)[:100] for m in dropped if isinstance(m, HumanMessage)][-5:]
    tools: list[str] = []
    for m in dropped:
        if isinstance(m, AIMessage):
            for call in m.tool_calls:
                if call["name"] not in tools:
                    tools.append(call["name"])
    line = "Older messages in this conversation were dropped to save space. The user earlier said: " + " | ".join(said)
    if tools:
        line += f". Tools used earlier: {', '.join(tools)}"
    return line + ". If you need lead or draft ids, call get_pipeline."


def trim_history(
    messages,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_tokens: int = MAX_HISTORY_TOKENS,
) -> tuple[list, str | None]:
    """Return (messages to send to the model, digest of what was dropped or None)."""
    msgs = list(messages)
    humans = [i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)]
    if not humans:
        return msgs, None
    last_human = humans[-1]

    def next_human(i: int) -> int:
        i = min(i, last_human)  # never start after the user's latest message
        while i < last_human and not isinstance(msgs[i], HumanMessage):
            i += 1
        return i

    start = next_human(max(0, len(msgs) - max_messages))
    while start < last_human and _estimate_tokens(msgs[start:]) > max_tokens:
        start = next_human(start + 1)

    kept = [
        _compact_tool_message(m) if isinstance(m, ToolMessage) and start + i < last_human else m
        for i, m in enumerate(msgs[start:])
    ]
    return kept, _digest(msgs[:start])
