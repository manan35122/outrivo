import pytest

from app import memory


@pytest.mark.usefixtures("clean_db")
def test_memories_are_per_user_and_upsert():
    memory.save_memory("alice", "business", "solar installer")
    memory.save_memory("alice", "business", "solar and batteries")
    memory.save_memory("bob", "business", "dental clinic")
    assert memory.load_memories("alice") == {"business": "solar and batteries"}
    assert memory.load_memories("bob") == {"business": "dental clinic"}
    assert memory.load_memories("carol") == {}


@pytest.mark.usefixtures("clean_db")
def test_save_facts_caps_the_number_of_keys(monkeypatch):
    monkeypatch.setattr(memory, "MAX_KEYS_PER_USER", 2)
    assert memory.save_facts("alice", {"business": "a", "offer": "b", "goals": "c"}) == 2
    # an existing key can still be updated when the user is at the cap
    assert memory.save_facts("alice", {"business": "a2"}) == 1
    assert memory.load_memories("alice")["business"] == "a2"


# ---- parse_facts: what is allowed to become a long-term memory ---------------


def test_parse_facts_keeps_allowed_keys_only():
    raw = 'Sure! {"business": "Runs PixelPush, a marketing agency", "favourite_colour": "blue", "Tone": "friendly"}'
    assert memory.parse_facts(raw) == {"business": "Runs PixelPush, a marketing agency", "tone": "friendly"}


def test_parse_facts_drops_secrets_and_contact_details():
    raw = (
        '{"business": "password is hunter2", "offer": "card 4111 1111 1111 1111", '
        '"goals": "call me on 0300-555-0199", "name": "mail me at a@b.com", '
        '"tone": "api key: sk-ant-abc123def456", "location": "Lahore"}'
    )
    assert memory.parse_facts(raw) == {"location": "Lahore"}


@pytest.mark.parametrize("raw", ["", "no json here", "{broken", "[1, 2]", '{"business": {"nested": 1}}'])
def test_parse_facts_handles_garbage(raw):
    assert memory.parse_facts(raw) == {}


def test_parse_facts_truncates_long_values_and_joins_lists():
    facts = memory.parse_facts('{"goals": ["more clients", "more revenue"], "offer": "' + "x" * 500 + '"}')
    assert facts["goals"] == "more clients, more revenue"
    assert len(facts["offer"]) == memory.MAX_VALUE_CHARS
