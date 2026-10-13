"""Tests for interval splitting algorithms under retroactive and overlapping updates."""
from datetime import datetime, timezone
import pytest

from app.domain.temporal import split_interval


@pytest.fixture
def t0() -> datetime:
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def t1() -> datetime:
    return datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def t2() -> datetime:
    return datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def t3() -> datetime:
    return datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_split_interval_carve_middle(t0, t1, t2, t3):
    """Carving [t1, t2) out of [t0, t3) splits into prefix [t0, t1) and suffix [t2, t3)."""
    fragments = split_interval(t0, t3, t1, t2)
    assert len(fragments) == 2
    assert fragments[0] == (t0, t1)
    assert fragments[1] == (t2, t3)


def test_split_interval_truncate_head(t0, t1, t2):
    """Cutting [t0, t1) out of [t0, t2) leaves only suffix [t1, t2)."""
    fragments = split_interval(t0, t2, t0, t1)
    assert len(fragments) == 1
    assert fragments[0] == (t1, t2)


def test_split_interval_truncate_tail(t0, t1, t2):
    """Cutting [t1, t2) out of [t0, t2) leaves only prefix [t0, t1)."""
    fragments = split_interval(t0, t2, t1, t2)
    assert len(fragments) == 1
    assert fragments[0] == (t0, t1)


def test_split_interval_complete_engulfment(t0, t1, t2, t3):
    """Cutting [t0, t3) out of [t1, t2) completely eliminates the existing interval."""
    fragments = split_interval(t1, t2, t0, t3)
    assert len(fragments) == 0


def test_split_interval_no_overlap(t0, t1, t2, t3):
    """Non-overlapping cut preserves the original interval unmodified."""
    fragments = split_interval(t0, t1, t2, t3)
    assert len(fragments) == 1
    assert fragments[0] == (t0, t1)


def test_split_interval_open_ended_carved_by_finite(t0, t1, t2):
    """Cutting finite [t1, t2) out of open-ended [t0, None) leaves prefix [t0, t1) and suffix [t2, None)."""
    fragments = split_interval(t0, None, t1, t2)
    assert len(fragments) == 2
    assert fragments[0] == (t0, t1)
    assert fragments[1] == (t2, None)


def test_split_interval_open_ended_carved_by_open_ended(t0, t1):
    """Cutting open-ended [t1, None) out of open-ended [t0, None) leaves prefix [t0, t1)."""
    fragments = split_interval(t0, None, t1, None)
    assert len(fragments) == 1
    assert fragments[0] == (t0, t1)
