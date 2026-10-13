"""Tests for strict timezone-aware timestamp validation and UTC normalization."""
from datetime import datetime, timedelta, timezone
import pytest

from app.domain.timestamps import (
    validate_and_normalize_optional_utc,
    validate_and_normalize_utc,
)


def test_accept_utc_timestamp_with_z():
    """Verify ISO string with 'Z' is accepted and has UTC tzinfo."""
    dt = validate_and_normalize_utc("2026-06-01T12:00:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 1
    assert dt.hour == 12


def test_accept_utc_timestamp_with_zero_offset():
    """Verify ISO string with '+00:00' is accepted."""
    dt = validate_and_normalize_utc("2026-06-01T12:00:00+00:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12


def test_normalize_positive_offset_to_utc():
    """Verify non-UTC offset (+05:30) is normalized to UTC."""
    # 17:30 in India (+05:30) is 12:00 in UTC
    dt = validate_and_normalize_utc("2026-06-01T17:30:00+05:30")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12
    assert dt.minute == 0


def test_normalize_negative_offset_to_utc():
    """Verify negative offset (-04:00) is normalized to UTC."""
    # 08:00 in EDT (-04:00) is 12:00 in UTC
    dt = validate_and_normalize_utc("2026-06-01T08:00:00-04:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12


def test_normalize_python_datetime_with_tz():
    """Verify Python datetime object with timezone is normalized."""
    ist = timezone(timedelta(hours=5, minutes=30))
    source_dt = datetime(2026, 6, 1, 17, 30, 0, tzinfo=ist)
    dt = validate_and_normalize_utc(source_dt)
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12


def test_reject_naive_iso_string():
    """Verify naive ISO string without timezone is strictly rejected."""
    with pytest.raises(ValueError, match="Naive timestamp rejected"):
        validate_and_normalize_utc("2026-06-01T12:00:00")


def test_reject_naive_datetime_object():
    """Verify naive Python datetime object is strictly rejected."""
    naive_dt = datetime(2026, 6, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="Naive timestamp rejected"):
        validate_and_normalize_utc(naive_dt)


def test_reject_invalid_string():
    """Verify malformed timestamp string is rejected."""
    with pytest.raises(ValueError, match="Invalid ISO-8601"):
        validate_and_normalize_utc("not-a-date")


def test_reject_none_in_required_validator():
    """Verify None raises ValueError in validate_and_normalize_utc."""
    with pytest.raises(ValueError, match="Timestamp cannot be None"):
        validate_and_normalize_utc(None)


def test_optional_utc_validator():
    """Verify validate_and_normalize_optional_utc handles None, empty string, and valid values."""
    assert validate_and_normalize_optional_utc(None) is None
    assert validate_and_normalize_optional_utc("") is None
    dt = validate_and_normalize_optional_utc("2026-01-01T00:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
