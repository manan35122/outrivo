import pytest

from app import usage


def test_estimate_cost_uses_configured_prices():
    # 100K input tokens is the top of the normal tier (1/10 of a million)
    assert usage.estimate_cost(100_000, 0) == pytest.approx(usage.PRICE_IN_PER_MTOK / 10)
    assert usage.estimate_cost(0, 1_000_000) == pytest.approx(usage.PRICE_OUT_PER_MTOK)


def test_prompts_over_100k_tokens_cost_five_times_more():
    normal = usage.estimate_cost(100_000, 1_000)
    long = usage.estimate_cost(100_001, 1_000)
    assert long == pytest.approx(normal * usage.LONG_PROMPT_MULTIPLIER, rel=0.01)


@pytest.mark.usefixtures("clean_db")
class TestWithDatabase:
    def test_record_and_summarise(self):
        cost = usage.record_usage("alice", "t1", 1000, 200)
        assert cost == pytest.approx(usage.estimate_cost(1000, 200))
        usage.record_usage("bob", "t2", 500, 100)
        s = usage.spend_summary()
        assert (s["tokens_in"], s["tokens_out"], s["chats"]) == (1500, 300, 2)
        assert s["spent_usd"] > 0

    def test_budget_ok_when_nothing_spent(self):
        assert usage.check_budget("alice") is None

    def test_user_daily_cap_is_per_user(self, monkeypatch):
        usage.record_usage("alice", "t1", 900, 200)
        monkeypatch.setattr(usage, "USER_DAILY_TOKEN_CAP", 1000)
        assert usage.check_budget("alice") == "user_daily_cap"
        assert usage.check_budget("bob") is None

    def test_global_budget_stops_everyone(self, monkeypatch):
        usage.record_usage("alice", "t1", 1_000_000, 0)
        monkeypatch.setattr(usage, "BUDGET_HARD_LIMIT_USD", 0.05)
        assert usage.check_budget("alice") == "global_budget"
        assert usage.check_budget("bob") == "global_budget"
