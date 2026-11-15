"""Production hardening for the HTTP layer (Stage 11 security review). No science lives here.

* SecurityHeadersMiddleware: nosniff, no framing, strict referrer policy, no device permissions.
* BodyLimitMiddleware: JSON requests here are a few hundred bytes; anything over the cap is refused before it is parsed.
* HeavyLimitMiddleware: the computing endpoints are CPU-bound (a cold scenario is ~25 s of one core). A bounded number run at once,
  the rest wait in a short queue and then get a typed 503 SERVER_BUSY, so one client cannot exhaust a small host.

All three are plain ASGI middleware, so they add no dependency and do not buffer responses.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Endpoints that compute (everything else is a cheap lookup). Matched on the path inside the API app.
HEAVY_PREFIXES = ("/horizon/profile", "/visibility/", "/scenarios/evaluate", "/scenarios/compare", "/scenarios/delay", "/engineering/solar")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "geolocation=(), camera=(), microphone=(), payment=(), usb=()",
    "cross-origin-opener-policy": "same-origin",
}


def _error_body(code: str, message: str, field: str | None = None) -> bytes:
    return json.dumps({"code": code, "message": message, "field": field, "details": {}, "request_id": None}).encode()


async def _respond(send: Send, status: int, body: bytes, extra: Iterable[tuple[bytes, bytes]] = ()) -> None:
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, extra: dict[str, str] | None = None) -> None:
        self.app = app
        self.headers = [(k.encode(), v.encode()) for k, v in {**SECURITY_HEADERS, **(extra or {})}.items()]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = [*message.get("headers", []), *[h for h in self.headers if h[0] not in present]]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    """Refuse request bodies over `max_bytes`, whether declared by Content-Length or streamed."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope.get("headers", [])).get(b"content-length")
        too_big = _error_body("INVALID_INPUT", f"Request body is larger than the {self.max_bytes}-byte limit.", "body")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            return await _respond(send, 413, too_big)
        seen = 0
        refused = False

        async def counting_receive() -> Message:
            nonlocal seen, refused
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    refused = True
                    return {"type": "http.request", "body": b"", "more_body": False}   # stop reading; the response below replaces the app's
            return message

        started = False

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if refused and not started:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, counting_receive, guarded_send)
        if refused and not started:
            await _respond(send, 413, too_big)


class HeavyLimitMiddleware:
    """At most `limit` computing requests run at once; others wait up to `queue_seconds`, then receive 503 SERVER_BUSY."""

    def __init__(self, app: ASGIApp, limit: int, queue_seconds: float, prefixes: tuple[str, ...] = HEAVY_PREFIXES,
                 on_busy: Callable[[str], Awaitable[None] | None] | None = None) -> None:
        self.app = app
        self.limit = max(1, limit)
        self.queue_seconds = queue_seconds
        self.prefixes = prefixes
        self.on_busy = on_busy
        self._sem: asyncio.Semaphore | None = None   # created lazily inside the running loop

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or scope.get("method") == "OPTIONS" or not path.startswith(self.prefixes):
            return await self.app(scope, receive, send)
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.limit)
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.queue_seconds)
        except TimeoutError:
            if self.on_busy:
                self.on_busy(path)
            return await _respond(send, 503, _error_body("SERVER_BUSY", "The server is computing other requests; please retry in a moment."),
                                  extra=[(b"retry-after", b"15")])
        try:
            await self.app(scope, receive, send)
        finally:
            self._sem.release()
