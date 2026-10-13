"""Tests for pure temporal interval containment, boundary guarantees, overlap, and intersection."""
from datetime import datetime, timedelta, timezone
import pytest

from app.domain.temporal import (
    interval_intersection,
    intervals_overlap,
    is_point_in_interval,
)


@pytest.fixture
def t0() -> datetime:
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def t1() -> datetime:
    return datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def t2() -> datetime:
    return datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_is_point_in_interval_exact_boundaries(t0, t1):
    """Verify half-open interval [t0, t1) boundary behavior."""
    # Point at exact start boundary -> True (inclusive)
    assert is_point_in_interval(t0, t0, t1) is True

    # Point at exact end boundary -> False (exclusive)
    assert is_point_in_interval(t1, t0, t1) is False

    # Point 1 microsecond before end -> True
    just_before_end = t1 - timedelta(microseconds=1)
    assert is_point_in_interval(just_before_end, t0, t1) is True

    # Point 1 microsecond before start -> False
    just_before_start = t0 - timedelta(microseconds=1)
    assert is_point_in_interval(just_before_start, t0, t1) is False


def test_is_point_in_interval_open_ended(t0):
    """Verify point containment in open-ended interval [t0, None)."""
    assert is_point_in_interval(t0, t0, None) is True
    future = t0 + timedelta(days=1000)
    assert is_point_in_interval(future, t0, None) is True

    past = t0 - timedelta(seconds=1)
    assert is_point_in_interval(past, t0, None) is False


def test_intervals_overlap_finite(t0, t1, t2):
    """Verify overlap between finite intervals."""
    # Clearly overlapping: [2026-01-01, 2026-08-01) and [2026-06-01, 2026-12-01)
    mid = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert intervals_overlap(t0, mid, t1, t2) is True


def test_intervals_overlap_adjacent_touching_boundary(t0, t1, t2):
    """Verify adjacent half-open intervals [t0, t1) and [t1, t2) do NOT overlap."""
    assert intervals_overlap(t0, t1, t1, t2) is False
    assert intervals_overlap(t1, t2, t0, t1) is False


def test_intervals_overlap_disjoint(t0, t1):
    """Verify disjoint intervals do not overlap."""
    t_gap_start = t1 + timedelta(days=10)
    t_gap_end = t1 + timedelta(days=20)
    assert intervals_overlap(t0, t1, t_gap_start, t_gap_end) is False


def test_intervals_overlap_open_ended(t0, t1):
    """Verify overlap with open-ended intervals."""
    # [t0, None) and [t1, None) always overlap after t1
    assert intervals_overlap(t0, None, t1, None) is True

    # [t0, t1) and [t1, None) touch at t1 -> do NOT overlap
    assert intervals_overlap(t0, t1, t1, None) is False

    # [t0, t1) and [t0 - 1 day, None) overlap
    t_early = t0 - timedelta(days=1)
    assert intervals_overlap(t0, t1, t_early, None) is True


def test_interval_intersection(t0, t1, t2):
    """Verify calculation of interval intersection."""
    # Overlapping intervals [t0, t2) and [t1, None) intersect at [t1, t2)
    intersection = interval_intersection(t0, t2, t1, None)
    assert intersection == (t1, t2)

    # Disjoint intervals return None
    assert interval_intersection(t0, t1, t1, t2) is None
