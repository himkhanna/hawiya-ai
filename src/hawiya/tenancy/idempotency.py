"""Idempotency-Key middleware for POST endpoints.

Per CLAUDE.md API conventions: ``Idempotency-Key`` is required on POSTs
that create resources, and the same key replayed within the TTL must
return the same response.

Phase 1 ships an in-memory store. It is correct for single-instance
dev/staging deployments and cleanly testable. Production hardening in
BUILD_PLAN week 4 will swap in a Postgres-backed store via the same
``IdempotencyStore`` Protocol — the middleware does not need to change.

Behaviour:

- Non-POST requests pass through unchanged.
- POSTs without ``Idempotency-Key`` pass through unchanged.
- A POST with a key is fingerprinted by ``(tenant_id, key, body_hash)``.
  - Cache hit + matching fingerprint → return the cached response.
  - Cache hit + different body → 422 ``IDEMPOTENCY_KEY_CONFLICT``.
  - Cache miss → forward, capture the response, and cache it for the TTL.

The middleware is positioned OUTSIDE the tenancy middleware so it never
tries to cache a 401-response — it short-circuits when ``X-Tenant-ID`` is
missing or invalid and lets tenancy reject normally.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_TTL_SECONDS = 24 * 60 * 60
TENANT_HEADER = b"x-tenant-id"
IDEMPOTENCY_HEADER = b"idempotency-key"

# Cache only successful responses; clients should retry transient errors.
_CACHEABLE_STATUS_MIN = 200
_CACHEABLE_STATUS_MAX = 300


@dataclass
class CachedResponse:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes
    body_hash: str
    expires_at: float


class IdempotencyStore(Protocol):
    async def get(self, tenant_id: uuid.UUID, key: str) -> CachedResponse | None: ...
    async def put(self, tenant_id: uuid.UUID, key: str, value: CachedResponse) -> None: ...


@dataclass
class InMemoryIdempotencyStore:
    """Process-local store. Single-instance only — see module docstring."""

    _entries: dict[tuple[uuid.UUID, str], CachedResponse] = field(default_factory=dict)

    async def get(self, tenant_id: uuid.UUID, key: str) -> CachedResponse | None:
        entry = self._entries.get((tenant_id, key))
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._entries.pop((tenant_id, key), None)
            return None
        return entry

    async def put(self, tenant_id: uuid.UUID, key: str, value: CachedResponse) -> None:
        self._entries[(tenant_id, key)] = value

    def clear(self) -> None:
        self._entries.clear()


def _header_lookup(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    for k, v in headers:
        if k.lower() == name:
            return v
    return None


def _conflict_response(request_id: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = (
        b'{"error":{"code":"IDEMPOTENCY_KEY_CONFLICT",'
        b'"message":"Idempotency-Key was previously used with a different request body.",'
        b'"details":{},"trace_id":"' + request_id.encode() + b'"}}'
    )
    return (
        422,
        [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        body,
    )


class IdempotencyMiddleware:
    """ASGI middleware enforcing Idempotency-Key on POST requests."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        store: IdempotencyStore | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.app = app
        self.store = store or InMemoryIdempotencyStore()
        self.ttl_seconds = ttl_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        raw_key = _header_lookup(headers, IDEMPOTENCY_HEADER)
        raw_tenant = _header_lookup(headers, TENANT_HEADER)
        if not raw_key or not raw_tenant:
            await self.app(scope, receive, send)
            return
        try:
            tenant_id = uuid.UUID(raw_tenant.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            await self.app(scope, receive, send)
            return
        key = raw_key.decode("utf-8", errors="replace")

        # Buffer the request body so we can hash it and re-emit to downstream.
        body = await self._collect_body(receive)
        body_hash = hashlib.sha256(body).hexdigest()

        cached = await self.store.get(tenant_id, key)
        if cached is not None:
            if cached.body_hash != body_hash:
                status, hdrs, payload = _conflict_response(key)
                await send({"type": "http.response.start", "status": status, "headers": hdrs})
                await send({"type": "http.response.body", "body": payload})
                return
            await send(
                {
                    "type": "http.response.start",
                    "status": cached.status,
                    "headers": cached.headers,
                }
            )
            await send({"type": "http.response.body", "body": cached.body})
            return

        # Miss — forward the request and capture the response for caching.
        await self.app(
            scope,
            _make_replay_receive(body),
            _make_capturing_send(
                send,
                store=self.store,
                tenant_id=tenant_id,
                key=key,
                body_hash=body_hash,
                ttl=self.ttl_seconds,
            ),
        )

    @staticmethod
    async def _collect_body(receive: Receive) -> bytes:
        chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            chunks.append(message.get("body", b""))
            more = bool(message.get("more_body"))
        return b"".join(chunks)


def _make_replay_receive(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _make_capturing_send(
    downstream: Send,
    *,
    store: IdempotencyStore,
    tenant_id: uuid.UUID,
    key: str,
    body_hash: str,
    ttl: int,
) -> Send:
    captured: dict[str, Any] = {"status": 200, "headers": [], "body": bytearray()}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            captured["body"].extend(chunk)
            if not message.get("more_body") and (
                _CACHEABLE_STATUS_MIN <= captured["status"] < _CACHEABLE_STATUS_MAX
            ):
                await store.put(
                    tenant_id,
                    key,
                    CachedResponse(
                        status=captured["status"],
                        headers=captured["headers"],
                        body=bytes(captured["body"]),
                        body_hash=body_hash,
                        expires_at=time.time() + ttl,
                    ),
                )
        await downstream(message)

    return send


# Type-checker happiness: ensure Awaitable / Callable are referenced.
_unused: tuple[Any, ...] = (Awaitable, Callable)
