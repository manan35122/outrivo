"""Runs one chat turn: builds the graph once, calls it, and shapes the API response."""

import logging
import threading

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from . import usage
from .callbacks import RunCollector
from .config import ANTHROPIC_API_KEY, LLM_TIMEOUT_SECONDS, MAX_OUTPUT_TOKENS, MODEL_NAME, TEMPERATURE
from .db import get_pool
from .graph import EMPTY_REPLY, build_graph
from .history import text_of
from .safety import redact

log = logging.getLogger("outrivo.chat")

RECURSION_LIMIT = 30  # last-resort backstop; the per-turn tool cap normally stops far earlier
FRIENDLY_ERROR = "Sorry, something went wrong on my side. Please try again in a moment."

_graph = None
_graph_lock = threading.Lock()


def thread_key(user_id: str, thread_id: str) -> str:
    """The id the checkpointer stores a conversation under.

    It includes the user_id (length-prefixed, so no two pairs can collide), so two users can
    never share or read a thread, even if they send the identical thread_id string.
    """
    return f"{len(user_id)}:{user_id}:{thread_id}"


def _model(max_tokens: int) -> ChatAnthropic:
    extra = {"temperature": TEMPERATURE} if TEMPERATURE is not None else {}
    return ChatAnthropic(
        model=MODEL_NAME,
        api_key=ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=2,
        **extra,
    )


def get_graph():
    """Build the graph on first use. A failed build is retried on the next request."""
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                checkpointer = PostgresSaver(get_pool())
                checkpointer.setup()  # creates the checkpoint tables if they do not exist yet
                _graph = build_graph(
                    main_llm=_model(MAX_OUTPUT_TOKENS),
                    classifier_llm=_model(5),
                    extractor_llm=_model(300),
                    checkpointer=checkpointer,
                )
    return _graph


def warm_up() -> None:
    """Called in the background at startup so the first real request is not slow."""
    try:
        get_graph()
        log.info("graph ready")
    except Exception:
        log.exception("warm-up failed (will retry on the first request)")


def _final_reply(result: dict) -> str:
    for message in reversed(result.get("messages", [])):
        if isinstance(message, AIMessage):
            text = text_of(message).strip()
            if text:
                return text
    return EMPTY_REPLY


def run_chat(user_id: str, thread_id: str, message: str, request_id: str | None = None) -> dict:
    collector = RunCollector()
    config = {
        "configurable": {
            "thread_id": thread_key(user_id, thread_id),
            "user_id": user_id,
            "request_id": request_id,
        },
        "callbacks": [collector],
        "recursion_limit": RECURSION_LIMIT,
    }
    error = None
    try:
        result = get_graph().invoke({"messages": [HumanMessage(content=message)]}, config)
        reply = _final_reply(result)
    except Exception:
        log.exception("chat failed user=%s", user_id)
        reply, error = FRIENDLY_ERROR, "agent_error"

    reply, _ = redact(reply)
    try:
        if collector.tokens_in or collector.tokens_out:
            usage.record_usage(user_id, thread_id, collector.tokens_in, collector.tokens_out)
    except Exception:
        log.exception("could not record usage")

    response = {
        "reply": reply,
        "tool_calls": collector.tool_calls,
        "tokens": {"in": collector.tokens_in, "out": collector.tokens_out},
    }
    if error:
        response["error"] = error
    return response
