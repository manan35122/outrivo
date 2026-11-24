"""Runs the REAL ChatAnthropic client against a local fake of the Anthropic Messages API.

No API key or network is needed. It proves what we send on the wire is well formed:
the tool schemas (no user_id / config leaking to the model), the system prompt, the
tool_use / tool_result round trip, and that token usage is read back correctly.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.postgres import PostgresSaver

from app import chat_service
from app.db import get_pool
from app.graph import build_graph

pytestmark = pytest.mark.usefixtures("clean_db")


def message(content, stop_reason, tokens=(50, 10)):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
    }


@pytest.fixture
def fake_anthropic():
    requests, replies = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
            payload = json.dumps(replies.pop(0)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", requests, replies
    server.shutdown()


def test_real_client_round_trip(fake_anthropic, monkeypatch):
    url, requests, replies = fake_anthropic

    def model(max_tokens):
        return ChatAnthropic(
            model="claude-haiku-5-5", api_key="test-key", base_url=url, max_tokens=max_tokens, max_retries=0
        )

    graph = build_graph(model(1200), model(5), model(300), PostgresSaver(get_pool()))
    monkeypatch.setattr(chat_service, "_graph", graph)

    replies += [
        message(
            [
                {"type": "text", "text": "Searching."},
                {"type": "tool_use", "id": "toolu_1", "name": "search_leads", "input": {"query": "dental clinic Lahore", "limit": 2}},
            ],
            "tool_use",
            (400, 30),
        ),
        message([{"type": "text", "text": "I found 2 dental clinics in Lahore."}], "end_turn", (600, 25)),
    ]
    res = chat_service.run_chat("alice", "t1", "Find me 2 dental clinics in Lahore", "r1")

    assert res["reply"] == "I found 2 dental clinics in Lahore."
    assert [c["name"] for c in res["tool_calls"]] == ["search_leads"]
    assert res["tool_calls"][0]["result"]["count"] == 2
    assert res["tokens"] == {"in": 1000, "out": 55}

    first, second = (r["body"] for r in requests)
    assert requests[0]["path"].endswith("/v1/messages")
    headers = requests[0]["headers"]  # the SDK picks the header; either carries the key
    assert "test-key" in (headers.get("x-api-key", "") + headers.get("authorization", ""))
    assert first["model"] == "claude-haiku-5-5" and first["max_tokens"] == 1200

    # five tools, and the model is never shown user_id, config or request_id
    tools = {t["name"]: t for t in first["tools"]}
    assert set(tools) == {"search_leads", "draft_outreach", "update_pipeline", "get_pipeline", "send_outreach"}
    for tool in tools.values():
        assert not {"user_id", "config", "request_id"} & set(tool["input_schema"].get("properties", {}))
    assert set(tools["draft_outreach"]["input_schema"]["required"]) == {"lead_id", "subject", "body"}

    system = first["system"] if isinstance(first["system"], str) else "".join(b["text"] for b in first["system"])
    assert "Outrivo" in system
    assert len(first["messages"]) == 1 and first["messages"][0]["role"] == "user"
    assert "Find me 2 dental clinics in Lahore" in json.dumps(first["messages"][0]["content"])

    # second request carries the assistant tool_use and the matching tool_result
    roles = [m["role"] for m in second["messages"]]
    assert roles == ["user", "assistant", "user"]
    tool_use = next(b for b in second["messages"][1]["content"] if b["type"] == "tool_use")
    tool_result = next(b for b in second["messages"][2]["content"] if b["type"] == "tool_result")
    assert tool_result["tool_use_id"] == tool_use["id"] == "toolu_1"
    assert json.loads(tool_result["content"] if isinstance(tool_result["content"], str) else tool_result["content"][0]["text"])["count"] == 2


def test_classifier_and_memory_calls_use_small_budgets(fake_anthropic, monkeypatch):
    url, requests, replies = fake_anthropic

    def model(max_tokens):
        return ChatAnthropic(
            model="claude-haiku-5-5", api_key="test-key", base_url=url, max_tokens=max_tokens, max_retries=0
        )

    graph = build_graph(model(1200), model(5), model(300), PostgresSaver(get_pool()))
    monkeypatch.setattr(chat_service, "_graph", graph)

    replies += [
        message([{"type": "text", "text": "ON"}], "end_turn", (80, 1)),
        message([{"type": "text", "text": "Happy to help."}], "end_turn", (300, 10)),
        message([{"type": "text", "text": '{"business": "Runs PixelPush"}'}], "end_turn", (120, 15)),
    ]
    res = chat_service.run_chat("alice", "t1", "Help me grow my order book. I run PixelPush", "r1")

    assert res["reply"] == "Happy to help."
    assert [r["body"]["max_tokens"] for r in requests] == [5, 1200, 300]
    assert "tools" not in requests[0]["body"] and "tools" not in requests[2]["body"]
    assert res["tokens"] == {"in": 500, "out": 26}

    from app import memory

    assert memory.load_memories("alice") == {"business": "Runs PixelPush"}
