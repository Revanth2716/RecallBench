"""Pure temporal interval operations adhering to [valid_from, valid_to) half-open semantics.

All datetime arguments must be timezone-aware (UTC).
"""
from datetime import datetime
from typing import List, Optional, Tuple

from .timestamps import validate_and_normalize_optional_utc, validate_and_normalize_utc


def is_point_in_interval(point: datetime, start: datetime, end: Optional[datetime]) -> bool:
    """Check if point falls within the half-open interval [start, end).

    Semantics:
    - start <= point < end (when end is finite)
    - start <= point (when end is None / open-ended infinity)

    Boundary guarantees:
    - point == start -> True
    - point == end   -> False
    """
    p = validate_and_normalize_utc(point)
    s = validate_and_normalize_utc(start)
    e = validate_and_normalize_optional_utc(end)

    if p < s:
        return False
    if e is not None and p >= e:
        return False
    return True


def intervals_overlap(
    start1: datetime, end1: Optional[datetime], start2: datetime, end2: Optional[datetime]
) -> bool:
    """Check if two half-open intervals [start1, end1) and [start2, end2) overlap.

    Two half-open intervals overlap iff: max(start1, start2) < min(end1, end2).
    Adjacent intervals touching at a single boundary (e.g. end1 == start2) do NOT overlap.
    """
    s1 = validate_and_normalize_utc(start1)
    e1 = validate_and_normalize_optional_utc(end1)
    s2 = validate_and_normalize_utc(start2)
    e2 = validate_and_normalize_optional_utc(end2)

    latest_start = max(s1, s2)

    if e1 is None and e2 is None:
        # Both intervals are open-ended to infinity, so they always overlap after latest_start
        return True
    elif e1 is None:
        earliest_end = e2
    elif e2 is None:
        earliest_end = e1
    else:
        earliest_end = min(e1, e2)

    # In half-open intervals, overlap requires latest_start < earliest_end
    return latest_start < earliest_end  # type: ignore[operator]


def interval_intersection(
    start1: datetime, end1: Optional[datetime], start2: datetime, end2: Optional[datetime]
) -> Optional[Tuple[datetime, Optional[datetime]]]:
    """Calculate the intersection [start, end) of two half-open intervals.

    Returns:
        (intersection_start, intersection_end) if overlap exists, else None.
    """
    if not intervals_overlap(start1, end1, start2, end2):
        return None

    s1 = validate_and_normalize_utc(start1)
    e1 = validate_and_normalize_optional_utc(end1)
    s2 = validate_and_normalize_utc(start2)
    e2 = validate_and_normalize_optional_utc(end2)

    intersect_start = max(s1, s2)
    if e1 is None and e2 is None:
        intersect_end = None
    elif e1 is None:
        intersect_end = e2
    elif e2 is None:
        intersect_end = e1
    else:
        intersect_end = min(e1, e2)

    return (intersect_start, intersect_end)


def split_interval(
    existing_start: datetime,
    existing_end: Optional[datetime],
    cutting_start: datetime,
    cutting_end: Optional[datetime],
) -> List[Tuple[datetime, Optional[datetime]]]:
    """Deterministically split an existing interval [existing_start, existing_end)
    by excising a cutting interval [cutting_start, cutting_end).

    Returns a list of remaining, non-overlapping sub-intervals of the existing interval.
    Possible return outcomes:
    - [(existing_start, existing_end)] if no overlap occurred.
    - [] if the cutting interval completely encompassed the existing interval.
    - [prefix_interval] if only the end was truncated.
    - [suffix_interval] if only the beginning was truncated.
    - [prefix_interval, suffix_interval] if the cut carved through the middle.
    """
    s_e = validate_and_normalize_utc(existing_start)
    e_e = validate_and_normalize_optional_utc(existing_end)
    s_c = validate_and_normalize_utc(cutting_start)
    e_c = validate_and_normalize_optional_utc(cutting_end)

    if not intervals_overlap(s_e, e_e, s_c, e_c):
        return [(s_e, e_e)]

    remaining: List[Tuple[datetime, Optional[datetime]]] = []

    # 1. Check for pre-cut prefix: [s_e, s_c)
    if s_e < s_c:
        remaining.append((s_e, s_c))

    # 2. Check for post-cut suffix: [e_c, e_e)
    if e_c is not None:
        if e_e is None:
            # Existing interval was open-ended; suffix continues to infinity
            remaining.append((e_c, None))
        elif e_c < e_e:
            # Suffix remains up to existing finite end
            remaining.append((e_c, e_e))

    return remaining
