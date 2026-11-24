"""The Outrivo LangGraph.

    START -> guard -> agent <-> tools
                |        |
                |        +-> memory -> END
                +-> END   (blocked: injection, other user's data, off-topic)

Nodes:
  guard   Guard Agent      rules first, then a tiny ON/OFF classifier call only when unclear
  agent   Outreach Agent   the main model (claude-haiku-5-5) with the 5 tools bound
  tools   Tool Executor    runs the model's tool calls, one at a time, with user_id from config
  memory  Memory Agent     extracts durable business facts and saves them per user_id

Per-request values (user_id, request_id) arrive in config["configurable"], set by the server.
Nodes take the models as arguments so tests can pass a scripted fake model.
"""

import json
import logging
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from . import safety
from .config import MAX_TOOL_CALLS_PER_TURN
from .history import text_of, trim_history
from .memory import load_memories, parse_facts, save_facts
from .prompts import CLASSIFIER_USER, EXTRACT_PROMPT, build_system_prompt
from .tools import ALL_TOOLS

log = logging.getLogger("outrivo.graph")

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
STEP_LIMIT_REPLY = (
    "I reached my step limit for one message. Tell me what you'd like to do next "
    "and I'll continue from where I stopped."
)
EMPTY_REPLY = "Sorry, I couldn't put together a reply. Could you rephrase that?"
# Facts are only extracted when the user is talking about themselves.
SELF_CUE = re.compile(
    r"\b(i|we)\s+(am|are|run|own|sell|offer|provide|help|work|manage|operate|started|founded|specialize|specialise|"
    r"prefer|like|usually|always|never|target|serve|do|have|need)\b"
    r"|\b(i'm|im|we're|we've|i've|remember|call me)\b"
    r"|\b(my|our)\s+(business|company|agency|clinic|firm|startup|store|shop|name|product|service|offer|tone|"
    r"target|clients?|customers?|team|goal|style|preference)s?\b",
    re.IGNORECASE,
)


class State(TypedDict):
    messages: Annotated[list, add_messages]
    blocked: bool


def _user_id(config) -> str:
    return (config.get("configurable") or {})["user_id"]


def _turn_tool_count(messages) -> int:
    """Tool results since the user's latest message (the current turn)."""
    count = 0
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, ToolMessage):
            count += 1
    return count


def build_graph(main_llm, classifier_llm, extractor_llm, checkpointer=None):
    llm_with_tools = main_llm.bind_tools(ALL_TOOLS)

    # ---- guard -------------------------------------------------------------
    def guard_node(state: State, config) -> dict:
        message = state["messages"][-1]
        text = text_of(message)

        refusal = None
        if safety.looks_like_injection(text):
            refusal = safety.REFUSAL_INJECTION
        elif safety.asks_for_other_users_data(text):
            refusal = safety.REFUSAL_OTHER_USER
        elif not safety.is_obviously_on_topic(text, has_history=len(state["messages"]) > 1):
            try:
                verdict = classifier_llm.invoke(
                    [SystemMessage(safety.CLASSIFIER_PROMPT), HumanMessage(CLASSIFIER_USER.format(message=text[:500]))],
                    config,
                )
                if "OFF" in text_of(verdict).upper():
                    refusal = safety.REFUSAL_OFF_TOPIC
            except Exception:
                # If the classifier is down, the agent's own prompt still refuses off-topic requests.
                log.exception("topic classifier failed; letting the message through")

        if refusal is None:
            return {"blocked": False}
        # Replace the stored user message so a blocked attack never sits in the thread history.
        return {
            "blocked": True,
            "messages": [
                HumanMessage(content=safety.REMOVED_MESSAGE, id=message.id),
                AIMessage(content=refusal),
            ],
        }

    # ---- agent -------------------------------------------------------------
    def agent_node(state: State, config) -> dict:
        try:
            memories = load_memories(_user_id(config))
        except Exception:
            log.exception("could not load memories; continuing without them")
            memories = {}
        history, digest = trim_history(state["messages"])
        system = SystemMessage(build_system_prompt(memories, digest))

        response = llm_with_tools.invoke([system, *history], config)

        if response.tool_calls and _turn_tool_count(state["messages"]) + len(response.tool_calls) > MAX_TOOL_CALLS_PER_TURN:
            # Replacing the message (same id) also removes its dangling tool calls from the thread.
            return {"messages": [AIMessage(content=STEP_LIMIT_REPLY, id=response.id)]}
        if not response.tool_calls and not text_of(response).strip():
            return {"messages": [AIMessage(content=EMPTY_REPLY, id=response.id)]}
        return {"messages": [response]}

    # ---- tools -------------------------------------------------------------
    def tools_node(state: State, config) -> dict:
        results = []
        for call in state["messages"][-1].tool_calls:
            tool = TOOLS_BY_NAME.get(call["name"])
            try:
                if tool is None:
                    raise ValueError("unknown tool")
                results.append(tool.invoke(call, config))
            except Exception:
                log.warning("tool call rejected: %s", call["name"], exc_info=True)
                results.append(
                    ToolMessage(
                        content=json.dumps({"error": f"Invalid call to {call['name']}. Check the arguments and try again."}),
                        tool_call_id=call["id"],
                        name=call["name"],
                        status="error",
                    )
                )
        return {"messages": results}

    # ---- memory ------------------------------------------------------------
    def memory_node(state: State, config) -> dict:
        try:
            text = next((text_of(m) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
            if len(text) < 12 or not SELF_CUE.search(text):
                return {}
            raw = extractor_llm.invoke(
                [SystemMessage(EXTRACT_PROMPT), HumanMessage(text[:1500])], config
            )
            save_facts(_user_id(config), parse_facts(text_of(raw)))
        except Exception:
            # Memory is best effort: a failure here must never lose the reply the user already earned.
            log.exception("memory extraction failed")
        return {}

    # ---- wiring ------------------------------------------------------------
    def after_guard(state: State) -> str:
        return END if state.get("blocked") else "agent"

    def after_agent(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else "memory"

    graph = StateGraph(State)
    graph.add_node("guard", guard_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("memory", memory_node)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard, {END: END, "agent": "agent"})
    graph.add_conditional_edges("agent", after_agent, {"tools": "tools", "memory": "memory"})
    graph.add_edge("tools", "agent")
    graph.add_edge("memory", END)
    return graph.compile(checkpointer=checkpointer)
