"""Timestamp validation and UTC normalization utilities.

Enforces zero-tolerance for naive timestamps:
- Rejects any timestamp without explicit timezone information.
- Normalizes timezone-aware timestamps with non-UTC offsets to UTC.
"""
from datetime import datetime, timezone
from typing import Annotated, Any, Optional
from pydantic import BeforeValidator


def validate_and_normalize_utc(v: Any) -> datetime:
    """Validate that a timestamp is timezone-aware and normalize it to UTC.

    Raises:
        ValueError: If the input is not a datetime/ISO string or is naive (lacks timezone).
    """
    if v is None:
        raise ValueError("Timestamp cannot be None")

    dt: datetime
    if isinstance(v, str):
        # Handle ISO-8601 strings
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Timestamp string cannot be empty")
        try:
            # Python 3.11+ fromisoformat supports 'Z' and offsets like '+05:30'
            dt = datetime.fromisoformat(cleaned)
        except Exception as exc:
            raise ValueError(f"Invalid ISO-8601 timestamp format: '{v}'") from exc
    elif isinstance(v, datetime):
        dt = v
    else:
        raise ValueError(f"Expected datetime or ISO string, got {type(v).__name__}")

    # Check for timezone awareness
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            f"Naive timestamp rejected: '{v}'. Timestamps must be timezone-aware (e.g. ISO-8601 ending in 'Z' or offset like '+05:30')."
        )

    # Normalize to UTC
    return dt.astimezone(timezone.utc)


def validate_and_normalize_optional_utc(v: Any) -> Optional[datetime]:
    """Validate and normalize an optional timestamp to UTC (allows None)."""
    if v is None or v == "":
        return None
    return validate_and_normalize_utc(v)


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


# Pydantic V2 annotated types for model fields
UtcDateTime = Annotated[datetime, BeforeValidator(validate_and_normalize_utc)]
OptionalUtcDateTime = Annotated[Optional[datetime], BeforeValidator(validate_and_normalize_optional_utc)]

# Convenience aliases
parse_utc_iso = validate_and_normalize_utc
now_utc = utc_now
