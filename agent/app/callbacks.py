"""Collects tokens and tool calls for ONE chat request, across every model and tool call
in the graph (guard classifier, main agent, memory extractor, tools)."""

import json
import threading

from langchain_core.callbacks import BaseCallbackHandler

MAX_RESULT_CHARS = 6000  # tool results stay structured JSON in the API response unless huge


def _result_value(output):
    raw = getattr(output, "content", output)
    if not isinstance(raw, str):
        raw = json.dumps(raw, default=str)
    if len(raw) > MAX_RESULT_CHARS:
        return raw[:MAX_RESULT_CHARS] + "...(shortened)"
    try:
        return json.loads(raw)
    except ValueError:
        return raw


class RunCollector(BaseCallbackHandler):
    def __init__(self) -> None:
        self.tokens_in = 0
        self.tokens_out = 0
        self.tool_calls: list[dict] = []
        self._by_run: dict = {}
        self._lock = threading.Lock()

    def on_chat_model_start(self, serialized, messages, **kwargs):
        pass

    def on_llm_end(self, response, **kwargs):
        with self._lock:
            for generations in response.generations:
                for generation in generations:
                    usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                    if usage:
                        self.tokens_in += int(usage.get("input_tokens", 0))
                        self.tokens_out += int(usage.get("output_tokens", 0))

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name") or "unknown"
        entry = {"name": name, "args": inputs if isinstance(inputs, dict) else {}, "result": None}
        with self._lock:
            self.tool_calls.append(entry)
            self._by_run[run_id] = entry

    def on_tool_end(self, output, *, run_id, **kwargs):
        entry = self._by_run.get(run_id)
        if entry is not None:
            entry["result"] = _result_value(output)

    def on_tool_error(self, error, *, run_id, **kwargs):
        entry = self._by_run.get(run_id)
        if entry is not None:
            entry["result"] = {"error": "tool failed"}
