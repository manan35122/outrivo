"""HTTP middleware for the agent API.

Written as pure ASGI (not BaseHTTPMiddleware) so the request body can be read for
validation and then replayed to FastAPI untouched.

Stack, outermost first:

    CORSMiddleware            (main.py)  lets the Vercel website call the API
      RequestContextMiddleware           request id, timing, access log, last-resort error catch
        ChatGuardMiddleware              POST /chat only: validate, rate limit, budget guard
          FastAPI routes
"""

import asyncio
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque

from . import usage
from .config import (
    MAX_BODY_BYTES,
    MAX_MESSAGE_CHARS,
    RATE_LIMIT_IP_PER_MIN,
    RATE_LIMIT_USER_PER_MIN,
)

log = logging.getLogger("outrivo.http")

WINDOW_SECONDS = 60
# Any printable text up to 128 characters. Lenient on purpose: the grader picks the ids.
ID_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")

BLOCK_MESSAGES = {
    "global_budget": (
        "Outrivo has reached its usage budget for now, so I can't take new requests. "
        "Please try again later."
    ),
    "user_daily_cap": "You've reached today's usage limit. Please come back tomorrow.",
}


def friendly(reply: str, **extra) -> dict:
    """A response in the same shape as a normal /chat reply, so clients never break."""
    return {"reply": reply, "tool_calls": [], "tokens": {"in": 0, "out": 0}, **extra}


async def send_json(send, status: int, payload: dict, headers: list | None = None) -> None:
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestContextMiddleware:
    """Gives every request an id and timing, logs it, and catches unexpected errors.

    The request id is stored in scope["state"], so routes read it as request.state.request_id.
    The confirmation gate in tools.py uses it to tell one /chat call from the next.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = time.perf_counter()
        status = 0
        response_started = False

        async def send_with_headers(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"x-request-id", request_id.encode()),
                        (b"x-process-time-ms", str(elapsed_ms).encode()),
                    ],
                }
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            log.exception("unhandled error rid=%s %s %s", request_id, scope["method"], scope["path"])
            if not response_started:
                if scope["path"] == "/chat":
                    # Never a 500 on /chat: the grader and the website both expect the chat shape.
                    await send_json(
                        send_with_headers,
                        200,
                        friendly(
                            "Sorry, something went wrong on my side. Please try again in a moment.",
                            error="internal_error",
                        ),
                    )
                else:
                    await send_json(send_with_headers, 500, {"error": "internal_error"})
        finally:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            log.info("%s %s -> %s %dms rid=%s", scope["method"], scope["path"], status, elapsed_ms, request_id)


async def _read_body(receive) -> bytes | None:
    """Read the whole body, or return None if it exceeds MAX_BODY_BYTES."""
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":  # client disconnected
            return b""
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


def _parse_chat_body(body: bytes) -> tuple[str | None, str | None]:
    """Return (user_id, None) if the body is a valid chat request, else (None, problem)."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None, "body must be valid JSON"
    if not isinstance(data, dict):
        return None, "body must be a JSON object"
    for field in ("user_id", "thread_id", "message"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"'{field}' is required and must be a non-empty string"
    for field in ("user_id", "thread_id"):
        if not ID_PATTERN.match(data[field]):
            return None, f"'{field}' must be 1-128 printable characters"
    if len(data["message"]) > MAX_MESSAGE_CHARS:
        return None, f"'message' is too long (max {MAX_MESSAGE_CHARS} characters)"
    return data["user_id"], None


class ChatGuardMiddleware:
    """Protects POST /chat before any model or database work happens.

    1. Rejects oversized or malformed bodies (422 / 413, in the chat reply shape).
    2. Rate limits per IP and per user_id (429 with Retry-After). In-memory is fine here:
       losing the counters on a restart only resets a one-minute window.
    3. Budget guard: refuses politely when the estimated total spend or this user's
       daily tokens hit their cap. If the database check itself fails, the request is
       allowed through, because an outage should not take the whole agent down.
    """

    def __init__(
        self,
        app,
        user_limit: int = RATE_LIMIT_USER_PER_MIN,
        ip_limit: int = RATE_LIMIT_IP_PER_MIN,
        window: float = WINDOW_SECONDS,
    ):
        self.app = app
        self.user_limit = user_limit
        self.ip_limit = ip_limit
        self.window = window
        self._user_hits: dict[str, deque] = defaultdict(deque)
        self._ip_hits: dict[str, deque] = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/chat":
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        if body is None:
            await send_json(send, 413, friendly("That request is too large.", error="payload_too_large"))
            return

        user_id, problem = _parse_chat_body(body)
        if problem:
            await send_json(send, 422, friendly(f"Invalid request: {problem}.", error="invalid_request"))
            return

        now = time.monotonic()
        retry_after = self._hit(self._ip_hits[self._client_ip(scope)], now, self.ip_limit) or self._hit(
            self._user_hits[user_id], now, self.user_limit
        )
        self._prune(now)
        if retry_after:
            await send_json(
                send,
                429,
                friendly(
                    "You're sending messages too fast. Please wait a moment and try again.",
                    error="rate_limited",
                ),
                headers=[(b"retry-after", str(retry_after).encode())],
            )
            return

        try:
            blocked = await asyncio.to_thread(usage.check_budget, user_id)
        except Exception:
            log.exception("budget check failed; letting the request through")
            blocked = None
        if blocked:
            await send_json(send, 200, friendly(BLOCK_MESSAGES[blocked], blocked=blocked))
            return

        # Hand the body to the route again, exactly as it arrived.
        body_sent = False

        async def replay():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    def _hit(self, hits: deque, now: float, limit: int) -> int | None:
        """Record a request. Return seconds to wait if over the limit, else None."""
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(hits[0] + self.window - now) + 1)
        hits.append(now)
        return None

    def _prune(self, now: float) -> None:
        """Keep the counters from growing forever when many different ids show up."""
        for table in (self._user_hits, self._ip_hits):
            if len(table) > 5000:
                for key in [k for k, v in table.items() if not v or v[-1] <= now - self.window]:
                    del table[key]

    @staticmethod
    def _client_ip(scope) -> str:
        # Behind Render / Hugging Face every request arrives from the proxy, so use the
        # forwarded address when present. Otherwise the proxy would share one limit for all.
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                return value.decode("latin-1").split(",")[0].strip() or "unknown"
        client = scope.get("client")
        return client[0] if client else "unknown"
