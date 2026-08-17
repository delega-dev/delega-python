"""Webhook verification helpers."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

# Allowed clock skew for future-dated webhook timestamps (seconds).
_MAX_FUTURE_SKEW_SECONDS = 60


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
    age_seconds = (datetime.now(timezone.utc) - received_at).total_seconds()
    # Reject timestamps too old (replay) or meaningfully in the future. A
    # symmetric abs() window would have accepted a stamp up to the full
    # tolerance ahead; allow only a small forward skew for clock drift.
    if age_seconds > tolerance_seconds:
        raise ValueError("stale timestamp")
    if age_seconds < -_MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("timestamp too far in the future")

    expected_hex = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    # Compare the hex digests case-insensitively — the format check above
    # permits uppercase hex, but hexdigest() is always lowercase.
    if not hmac.compare_digest(expected_hex, signature_hex.lower()):
        raise ValueError("signature mismatch")

    return True
