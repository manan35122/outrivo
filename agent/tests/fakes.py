"""A scripted stand-in for ChatAnthropic, so the whole graph can be tested without an API key."""

import json
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


def say(text: str) -> AIMessage:
    return AIMessage(content=text)


def call(*calls) -> AIMessage:
    """call(("search_leads", {"query": "dental Lahore"}), ("get_pipeline", {}))"""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}
            for name, args in calls
        ],
    )


class ScriptedModel(BaseChatModel):
    """Returns the next scripted message on every call. An item may be a function of the
    messages it was sent. `seen` records every prompt, so tests can inspect what the model got."""

    script: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        if self.fail:
            raise RuntimeError("model is down")
        item = self.script.pop(0) if self.script else say("(script exhausted)")
        if callable(item):
            item = item(messages)
        item.usage_metadata = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
        return ChatResult(generations=[ChatGeneration(message=item)])


def facts(**kv) -> AIMessage:
    return say(json.dumps(kv))
