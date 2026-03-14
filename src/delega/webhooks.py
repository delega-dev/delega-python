"""Webhook verification helpers."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verify_webhook(
    payload: bytes,
    signature: str,
    timestamp: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify a Delega webhook signature.

    Args:
        payload: Raw request body bytes.
        signature: Value of the X-Delega-Signature header.
        timestamp: Value of the X-Delega-Timestamp header.
        secret: Your webhook secret.
        tolerance_seconds: Max age in seconds.

    Returns:
        True if the signature matches and the timestamp is within tolerance.

    Raises:
        ValueError: If the signature format is invalid, the timestamp is stale,
            or the signature does not match.
    """
    if not signature.startswith("sha256="):
        raise ValueError("bad signature format")

    signature_hex = signature[len("sha256=") :]
    if len(signature_hex) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in signature_hex):
        raise ValueError("bad signature format")

    received_at = _parse_timestamp(timestamp)
    age_seconds = abs((datetime.now(timezone.utc) - received_at).total_seconds())
    if age_seconds > tolerance_seconds:
        raise ValueError("stale timestamp")

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("signature mismatch")

    return True
