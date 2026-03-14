"""Webhook verification tests."""

from __future__ import annotations

import hashlib
import hmac
import unittest
from datetime import datetime, timedelta, timezone

from delega import verify_webhook


def _timestamp(delta: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat().replace("+00:00", "Z")


def _signature(payload: bytes, timestamp: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


class TestVerifyWebhook(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = b'{"event":"task.created","task":{"id":"abc123"}}'
        self.secret = "whsec_test_secret"

    def test_verifies_valid_signature(self) -> None:
        timestamp = _timestamp()
        signature = _signature(self.payload, timestamp, self.secret)

        self.assertTrue(
            verify_webhook(self.payload, signature, timestamp, self.secret)
        )

    def test_rejects_bad_signature_format(self) -> None:
        timestamp = _timestamp()

        with self.assertRaisesRegex(ValueError, "bad signature format"):
            verify_webhook(self.payload, "not-a-sha256", timestamp, self.secret)

    def test_rejects_stale_timestamp(self) -> None:
        timestamp = _timestamp(timedelta(minutes=-6))
        signature = _signature(self.payload, timestamp, self.secret)

        with self.assertRaisesRegex(ValueError, "stale timestamp"):
            verify_webhook(self.payload, signature, timestamp, self.secret)

    def test_rejects_signature_mismatch(self) -> None:
        timestamp = _timestamp()
        signature = _signature(self.payload, timestamp, "wrong_secret")

        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            verify_webhook(self.payload, signature, timestamp, self.secret)

    def test_rejects_invalid_timestamp(self) -> None:
        signature = _signature(self.payload, "not-a-timestamp", self.secret)

        with self.assertRaisesRegex(ValueError, "invalid timestamp"):
            verify_webhook(
                self.payload,
                signature,
                "not-a-timestamp",
                self.secret,
            )
