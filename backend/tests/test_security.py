"""Unit tests for API key generation and webhook signature verification."""

from __future__ import annotations

import time

from app.core.security import (
    derive_key_id,
    generate_api_key,
    generate_webhook_secret,
    hash_api_key_secret,
    verify_api_key,
    verify_webhook_signature,
    webhook_signature,
)


def test_generate_api_key_roundtrip() -> None:
    key = generate_api_key()
    assert key.raw.startswith("ctk_live_")
    assert key.id == derive_key_id(key.raw)
    assert hash_api_key_secret(key.raw) == key.hashed_secret
    assert verify_api_key(key.raw, key.hashed_secret) is True
    assert verify_api_key("bogus", key.hashed_secret) is False


def test_webhook_signature_roundtrip() -> None:
    secret = generate_webhook_secret()
    body = b'{"event":"inspection.failed","line_id":"x"}'
    sig = webhook_signature(secret, body)

    assert verify_webhook_signature(secret, body, sig) is True
    # tampered body
    assert verify_webhook_signature(secret, body + b"!", sig) is False
    # wrong secret
    assert verify_webhook_signature("nope", body, sig) is False


def test_webhook_signature_rejects_stale() -> None:
    secret = generate_webhook_secret()
    body = b'{"x":1}'
    # signed five hours ago
    stale = webhook_signature(secret, body, timestamp=int(time.time()) - 60 * 60 * 5)
    assert verify_webhook_signature(secret, body, stale) is False
    # but a reasonably recent one is fine
    recent = webhook_signature(secret, body, timestamp=int(time.time()) - 10)
    assert verify_webhook_signature(secret, body, recent) is True
