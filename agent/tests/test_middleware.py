import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app import middleware, usage

GOOD = {"user_id": "u1", "thread_id": "t1", "message": "hi"}


@pytest.fixture(autouse=True)
def no_db(monkeypatch):
    """These tests never touch the database: the budget check is replaced."""
    monkeypatch.setattr(usage, "check_budget", lambda user_id: None)


def build(user_limit=30, ip_limit=300):
    async def chat(request):
        data = await request.json()
        return JSONResponse({"echo": data, "request_id": request.state.request_id})

    async def chat_boom(request):
        raise RuntimeError("boom")

    async def health(request):
        return PlainTextResponse("ok")

    async def other_boom(request):
        raise RuntimeError("boom")

    def make(chat_handler):
        app = Starlette(
            routes=[
                Route("/chat", chat_handler, methods=["POST"]),
                Route("/health", health),
                Route("/boom", other_boom),
            ]
        )
        app.add_middleware(middleware.ChatGuardMiddleware, user_limit=user_limit, ip_limit=ip_limit)
        app.add_middleware(middleware.RequestContextMiddleware)
        return TestClient(app, raise_server_exceptions=False)

    return make(chat), make(chat_boom)


@pytest.fixture
def client():
    return build()[0]


# ---- request context ------------------------------------------------------


def test_valid_chat_passes_and_body_is_replayed(client):
    r = client.post("/chat", json=GOOD)
    assert r.status_code == 200
    assert r.json()["echo"] == GOOD
    assert r.headers["x-request-id"] == r.json()["request_id"]
    assert int(r.headers["x-process-time-ms"]) >= 0


def test_every_request_gets_a_different_id(client):
    ids = {client.post("/chat", json=GOOD).headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5


def test_other_routes_are_not_guarded(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.text == "ok" and "x-request-id" in r.headers


def test_unhandled_error_on_chat_returns_friendly_chat_shape():
    r = build()[1].post("/chat", json=GOOD)
    assert r.status_code == 200
    body = r.json()
    assert body["error"] == "internal_error"
    assert body["reply"] and body["tool_calls"] == [] and body["tokens"] == {"in": 0, "out": 0}


def test_unhandled_error_elsewhere_is_a_json_500(client):
    r = client.get("/boom")
    assert r.status_code == 500 and r.json() == {"error": "internal_error"}


# ---- validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"content": "not json"},
        {"json": [1, 2, 3]},
        {"json": {"user_id": "u1", "thread_id": "t1"}},
        {"json": {**GOOD, "message": "   "}},
        {"json": {**GOOD, "user_id": 123}},
        {"json": {**GOOD, "user_id": "bad\nid"}},
        {"json": {**GOOD, "thread_id": "x" * 200}},
        {"json": {**GOOD, "message": "x" * (middleware.MAX_MESSAGE_CHARS + 1)}},
    ],
)
def test_invalid_bodies_get_422_in_chat_shape(client, kwargs):
    r = client.post("/chat", **kwargs)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_request" and body["reply"] and body["tool_calls"] == []


def test_oversized_body_gets_413(client):
    r = client.post("/chat", json={**GOOD, "message": "x" * (middleware.MAX_BODY_BYTES + 10)})
    assert r.status_code == 413 and r.json()["error"] == "payload_too_large"


def test_ids_may_contain_spaces_and_unicode(client):
    r = client.post("/chat", json={**GOOD, "user_id": "test user 1", "thread_id": "ریاض-1"})
    assert r.status_code == 200


# ---- rate limiting --------------------------------------------------------


def test_rate_limit_per_user():
    client = build(user_limit=3)[0]
    assert [client.post("/chat", json=GOOD).status_code for _ in range(3)] == [200, 200, 200]
    blocked = client.post("/chat", json=GOOD)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json()["error"] == "rate_limited" and blocked.json()["reply"]
    # another user is unaffected
    assert client.post("/chat", json={**GOOD, "user_id": "u2"}).status_code == 200


def test_rate_limit_per_ip_uses_forwarded_address():
    client = build(ip_limit=2)[0]
    a = {"x-forwarded-for": "1.1.1.1, 10.0.0.1"}
    b = {"x-forwarded-for": "2.2.2.2"}
    assert client.post("/chat", json=GOOD, headers=a).status_code == 200
    assert client.post("/chat", json={**GOOD, "user_id": "u2"}, headers=a).status_code == 200
    assert client.post("/chat", json={**GOOD, "user_id": "u3"}, headers=a).status_code == 429
    assert client.post("/chat", json={**GOOD, "user_id": "u4"}, headers=b).status_code == 200


def test_rate_limit_window_expires():
    guard = middleware.ChatGuardMiddleware(app=None, user_limit=1, window=60)
    hits = guard._user_hits["u"]
    assert guard._hit(hits, now=0.0, limit=1) is None
    assert guard._hit(hits, now=10.0, limit=1) == 51
    assert guard._hit(hits, now=61.0, limit=1) is None


# ---- budget guard ---------------------------------------------------------


@pytest.mark.parametrize("reason", ["global_budget", "user_daily_cap"])
def test_budget_block_returns_polite_reply_and_skips_the_route(client, monkeypatch, reason):
    monkeypatch.setattr(usage, "check_budget", lambda user_id: reason)
    r = client.post("/chat", json=GOOD)
    body = r.json()
    assert r.status_code == 200 and body["blocked"] == reason
    assert body["reply"] == middleware.BLOCK_MESSAGES[reason]
    assert "echo" not in body


def test_budget_check_failure_lets_the_request_through(client, monkeypatch):
    def broken(user_id):
        raise RuntimeError("database down")

    monkeypatch.setattr(usage, "check_budget", broken)
    assert client.post("/chat", json=GOOD).status_code == 200


# ---- the real app ---------------------------------------------------------


def test_real_app_endpoints(monkeypatch):
    from app import chat_service
    from app.main import app

    seen = {}

    def fake_run_chat(user_id, thread_id, message, request_id=None):
        seen.update(user_id=user_id, thread_id=thread_id, message=message, request_id=request_id)
        return {"reply": "hello", "tool_calls": [], "tokens": {"in": 1, "out": 2}}

    monkeypatch.setattr(chat_service, "run_chat", fake_run_chat)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200 and health.text == "ok"

    chat = client.post("/chat", json=GOOD)
    body = chat.json()
    assert chat.status_code == 200
    assert set(body) == {"reply", "tool_calls", "tokens"}
    assert isinstance(body["tool_calls"], list) and set(body["tokens"]) == {"in", "out"}
    # the route passes the middleware's request id on, which the confirmation gate relies on
    assert seen["request_id"] == chat.headers["x-request-id"]
    assert (seen["user_id"], seen["thread_id"], seen["message"]) == ("u1", "t1", "hi")

    cors = client.get("/health", headers={"Origin": "https://example.vercel.app"})
    assert cors.headers["access-control-allow-origin"] == "*"
    assert client.post("/chat", json={"user_id": "u1"}).status_code == 422
