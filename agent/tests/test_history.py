import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.history import trim_history


def turn(i, with_tool=False):
    msgs = [HumanMessage(content=f"question {i}")]
    if with_tool:
        leads = [{"id": n, "company": f"Co{n}", "name": f"N{n}", "city": "Lahore", "stage": "new",
                  "email": "x@y.example", "phone": "123", "notes": "long note " * 20} for n in range(3)]
        msgs += [
            AIMessage(content="", tool_calls=[{"name": "search_leads", "args": {}, "id": f"c{i}", "type": "tool_call"}]),
            ToolMessage(content=json.dumps({"count": 3, "leads": leads}), tool_call_id=f"c{i}", name="search_leads"),
        ]
    msgs.append(AIMessage(content=f"answer {i}"))
    return msgs


def flat(turns):
    return [m for t in turns for m in t]


def test_short_history_is_untouched():
    msgs = flat([turn(1), turn(2)])
    kept, digest = trim_history(msgs)
    assert [m.content for m in kept] == [m.content for m in msgs] and digest is None


def test_long_history_keeps_recent_messages_starting_on_a_user_message():
    msgs = flat([turn(i) for i in range(30)])
    kept, digest = trim_history(msgs, max_messages=10)
    assert len(kept) <= 10 and isinstance(kept[0], HumanMessage)
    assert kept[-1].content == "answer 29"
    assert digest and "question" in digest and "get_pipeline" in digest


def test_never_starts_with_an_orphan_tool_result():
    msgs = flat([turn(i, with_tool=True) for i in range(10)])
    for limit in range(3, 20):
        kept, _ = trim_history(msgs, max_messages=limit)
        assert isinstance(kept[0], HumanMessage)
        ids_called = {c["id"] for m in kept if isinstance(m, AIMessage) for c in m.tool_calls}
        assert all(m.tool_call_id in ids_called for m in kept if isinstance(m, ToolMessage))


def test_current_turn_is_always_kept_even_when_it_is_long():
    current = [HumanMessage(content="find leads")]
    for n in range(8):
        current += [
            AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": f"x{n}", "type": "tool_call"}]),
            ToolMessage(content="ok", tool_call_id=f"x{n}", name="t"),
        ]
    kept, _ = trim_history(flat([turn(1), turn(2)]) + current, max_messages=5)
    assert kept[0].content == "find leads" and len(kept) == len(current)


def test_token_budget_drops_oldest_turns_first():
    big = [HumanMessage(content="x" * 4000), AIMessage(content="y" * 4000)]
    msgs = big + big + [HumanMessage(content="latest"), AIMessage(content="reply")]
    kept, digest = trim_history(msgs, max_messages=50, max_tokens=1500)
    assert kept[0].content == "latest" and digest


def test_old_tool_results_are_shrunk_but_current_ones_are_not():
    msgs = flat([turn(1, with_tool=True), turn(2, with_tool=True)])
    kept, _ = trim_history(msgs)
    tool_msgs = [m for m in kept if isinstance(m, ToolMessage)]
    old, current = json.loads(tool_msgs[0].content), json.loads(tool_msgs[1].content)
    assert set(old["leads"][0]) == {"id", "company", "name", "city", "stage"}
    assert "notes" in current["leads"][0]


def test_no_user_message_returns_input_as_is():
    msgs = [AIMessage(content="hello")]
    assert trim_history(msgs) == (msgs, None)
