import pytest

from app import tools

pytestmark = pytest.mark.usefixtures("clean_db")


def run(tool, args=None, user="alice", req="r1"):
    return tool.invoke(args or {}, config={"configurable": {"user_id": user, "request_id": req}})


def find(user="alice", query="dental clinic Lahore", limit=3):
    return run(tools.search_leads, {"query": query, "limit": limit}, user=user)


# ---- search_leads ---------------------------------------------------------


def test_search_finds_and_saves_leads():
    res = find()
    assert res["count"] == 3
    assert {l["city"] for l in res["leads"]} == {"Lahore"}
    assert all(l["stage"] == "new" and l["notes"] for l in res["leads"])
    assert run(tools.get_pipeline)["total"] == 3


def test_search_is_idempotent():
    first = [l["id"] for l in find()["leads"]]
    second = [l["id"] for l in find()["leads"]]
    assert first == second
    assert run(tools.get_pipeline)["total"] == 3


def test_search_city_is_a_hard_filter():
    res = find(query="solar installers in Islamabad", limit=5)
    assert res["count"] == 2
    assert {l["city"] for l in res["leads"]} == {"Islamabad"}


def test_search_without_city_uses_industry():
    res = find(query="Find me 3 solar installers")
    assert res["count"] == 3
    assert {l["industry"] for l in res["leads"]} == {"solar installer"}


def test_search_unknown_industry_gives_hint():
    res = find(query="bakery in Karachi")
    assert res["count"] == 0 and "Industries available" in res["hint"]


def test_search_needs_a_target():
    assert "error" in find(query="find me leads")


def test_search_limit_is_capped():
    assert find(query="Lahore", limit=50)["count"] <= tools.MAX_SEARCH_LIMIT


def test_model_cannot_see_or_set_user_id():
    for t in tools.ALL_TOOLS:
        assert "user_id" not in t.args and "config" not in t.args
    assert set(tools.search_leads.args) == {"query", "limit"}


# ---- draft_outreach -------------------------------------------------------


def test_draft_is_saved_not_sent():
    lead = find(limit=1)["leads"][0]
    res = run(tools.draft_outreach, {"lead_id": lead["id"], "subject": "Hi", "body": "Hello there"})
    assert res["status"] == "draft"
    row = run(tools.get_pipeline)["leads"][0]
    assert row["draft_ids"] == [res["outreach_id"]] and row["sent"] == 0


def test_redraft_replaces_previous_draft():
    lead = find(limit=1)["leads"][0]
    args = {"lead_id": lead["id"], "subject": "Hi", "body": "v1"}
    run(tools.draft_outreach, args)
    second = run(tools.draft_outreach, {**args, "body": "v2"})
    assert run(tools.get_pipeline)["leads"][0]["draft_ids"] == [second["outreach_id"]]


def test_draft_validation():
    lead = find(limit=1)["leads"][0]
    assert "error" in run(tools.draft_outreach, {"lead_id": lead["id"], "subject": "", "body": "x"})
    assert "error" in run(tools.draft_outreach, {"lead_id": lead["id"], "subject": "s", "body": ""})
    assert "error" in run(
        tools.draft_outreach, {"lead_id": lead["id"], "subject": "s", "body": "x", "channel": "fax"}
    )
    assert "error" in run(
        tools.draft_outreach, {"lead_id": lead["id"], "subject": "s", "body": "x" * 5000}
    )
    assert "error" in run(tools.draft_outreach, {"lead_id": 99999, "subject": "s", "body": "x"})


# ---- update_pipeline / get_pipeline ---------------------------------------


def test_update_pipeline():
    lead = find(limit=1)["leads"][0]
    res = run(tools.update_pipeline, {"lead_id": lead["id"], "stage": "Replied"})
    assert res["stage"] == "replied"
    assert run(tools.get_pipeline, {"stage": "replied"})["total"] == 1
    assert run(tools.get_pipeline)["by_stage"]["replied"] == 1


def test_update_pipeline_rejects_bad_stage_and_unknown_lead():
    lead = find(limit=1)["leads"][0]
    assert "error" in run(tools.update_pipeline, {"lead_id": lead["id"], "stage": "banana"})
    assert "error" in run(tools.update_pipeline, {"lead_id": 99999, "stage": "won"})


# ---- user isolation -------------------------------------------------------


def test_users_cannot_touch_each_others_data():
    lead = find(user="alice", limit=1)["leads"][0]
    draft = run(
        tools.draft_outreach, {"lead_id": lead["id"], "subject": "s", "body": "b"}, user="alice"
    )
    assert run(tools.get_pipeline, user="bob")["total"] == 0
    assert "error" in run(tools.update_pipeline, {"lead_id": lead["id"], "stage": "won"}, user="bob")
    assert "error" in run(
        tools.draft_outreach, {"lead_id": lead["id"], "subject": "s", "body": "b"}, user="bob"
    )
    assert "error" in run(tools.send_outreach, {"outreach_ids": [draft["outreach_id"]]}, user="bob")
    # alice's lead is untouched
    assert run(tools.get_pipeline, user="alice")["by_stage"]["new"] == 1


def test_two_users_can_hold_the_same_demo_lead():
    a = find(user="alice", limit=1)["leads"][0]
    b = find(user="bob", limit=1)["leads"][0]
    assert a["id"] != b["id"] and a["email"] == b["email"]


# ---- send_outreach confirmation gate --------------------------------------


def make_draft(user="alice", limit=1):
    ids = []
    for lead in find(user=user, limit=limit)["leads"]:
        ids.append(
            run(tools.draft_outreach, {"lead_id": lead["id"], "subject": "s", "body": "b"}, user=user)[
                "outreach_id"
            ]
        )
    return ids


def test_send_needs_confirmation_in_a_later_request():
    ids = make_draft()
    first = run(tools.send_outreach, {"outreach_ids": ids}, req="r1")
    assert first["status"] == "confirmation_required" and first["sent"] is False
    # same request again: still not sent (model cannot confirm its own question)
    again = run(tools.send_outreach, {"outreach_ids": ids}, req="r1")
    assert again["status"] == "confirmation_required"
    assert run(tools.get_pipeline)["leads"][0]["sent"] == 0
    # a later request (the user said yes): now it sends
    done = run(tools.send_outreach, {"outreach_ids": ids}, req="r2")
    assert done["status"] == "sent" and done["mode"] == "simulated"
    row = run(tools.get_pipeline)["leads"][0]
    assert row["sent"] == 1 and row["stage"] == "contacted" and row["draft_ids"] == []
    # cannot send twice
    assert "error" in run(tools.send_outreach, {"outreach_ids": ids}, req="r3")


def test_send_fails_closed_without_request_ids():
    ids = make_draft()
    cfg = {"configurable": {"user_id": "alice"}}
    for _ in range(3):
        res = tools.send_outreach.invoke({"outreach_ids": ids}, config=cfg)
        assert res["status"] == "confirmation_required"


def test_confirmation_covers_only_the_ids_that_were_confirmed():
    ids = make_draft(limit=2)
    run(tools.send_outreach, {"outreach_ids": ids}, req="r1")
    # the model changes the selection later: that needs its own confirmation
    res = run(tools.send_outreach, {"outreach_ids": ids[:1]}, req="r2")
    assert res["status"] == "confirmation_required"


def test_confirmation_does_not_cross_users():
    ids = make_draft(user="alice")
    run(tools.send_outreach, {"outreach_ids": ids}, user="alice", req="r1")
    assert "error" in run(tools.send_outreach, {"outreach_ids": ids}, user="bob", req="r2")


def test_send_batch_limit_and_empty():
    assert "error" in run(tools.send_outreach, {"outreach_ids": list(range(1, 12))})
    assert "error" in run(tools.send_outreach, {"outreach_ids": []})


# ---- tool-level middleware ------------------------------------------------


def test_missing_user_context_returns_error_not_exception():
    res = tools.get_pipeline.invoke({}, config={"configurable": {}})
    assert res == {"error": "No user in context."}
