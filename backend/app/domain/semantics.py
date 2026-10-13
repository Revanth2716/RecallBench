"""Domain-level resolution policies for updates, contradictions, and deletions.

These pure functions enforce deterministic memory lifecycle transitions
without depending on database cursors or network protocols.
"""
import uuid
from datetime import datetime
from typing import Any, List, Optional, Tuple

from .enums import (
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from .models import DeletionEvent, FactRecord, MemoryQuery, QueryPrediction, UpdateEvent
from .temporal import intervals_overlap, is_point_in_interval, split_interval


def apply_temporal_supersede(
    existing_facts: List[FactRecord], update: UpdateEvent
) -> Tuple[List[FactRecord], FactRecord]:
    """Apply an update event using TEMPORAL_SUPERSEDE semantics.

    1. Finds active facts for the (entity, attribute) that overlap with the new valid interval.
    2. Retracts or splits existing facts so their valid intervals do not collide with the new fact.
    3. Creates and returns the new FactRecord with incremented version.

    Returns:
        (updated_existing_facts, newly_created_fact)
    """
    new_fact_id = f"fact_{uuid.uuid4().hex[:8]}"
    new_start = update.effective_time
    new_end = update.valid_to

    modified_facts: List[FactRecord] = []
    max_prior_version = 0

    for fact in existing_facts:
        if fact.entity_id != update.entity_id or fact.attribute != update.attribute:
            modified_facts.append(fact)
            continue

        if fact.is_deleted or fact.retracted_at is not None:
            modified_facts.append(fact)
            continue

        max_prior_version = max(max_prior_version, fact.version)

        # Check for temporal overlap
        if intervals_overlap(fact.valid_from, fact.valid_to, new_start, new_end):
            # Calculate non-overlapping fragments
            fragments = split_interval(fact.valid_from, fact.valid_to, new_start, new_end)

            # The original fact record is retracted
            fact_data = fact.model_dump()
            fact_data["retracted_at"] = update.asserted_at
            fact_data["superseded_by"] = new_fact_id
            modified_facts.append(FactRecord(**fact_data))

            # Re-emit preserved fragments as split child records
            for idx, (frag_start, frag_end) in enumerate(fragments):
                frag_record = FactRecord(
                    id=f"{fact.id}_split_{idx}",
                    entity_id=fact.entity_id,
                    attribute=fact.attribute,
                    value=fact.value,
                    valid_from=frag_start,
                    valid_to=frag_end,
                    asserted_at=update.asserted_at,
                    retracted_at=None,
                    version=fact.version + 1,
                    superseded_by=None,
                    is_deleted=False,
                    confidence=fact.confidence,
                )
                modified_facts.append(frag_record)
        else:
            modified_facts.append(fact)

    # Instantiate the new fact
    new_fact = FactRecord(
        id=new_fact_id,
        entity_id=update.entity_id,
        attribute=update.attribute,
        value=update.new_value,
        valid_from=new_start,
        valid_to=new_end,
        asserted_at=update.asserted_at,
        retracted_at=None,
        version=max_prior_version + 1,
        superseded_by=None,
        is_deleted=False,
        confidence=update.confidence,
    )

    return modified_facts, new_fact


def resolve_contradiction(
    facts: List[FactRecord], policy: ContradictionPolicy
) -> Tuple[QueryStatus, Optional[FactRecord], Optional[Any]]:
    """Deterministically resolve a set of facts valid at the same query point.

    Returns:
        (QueryStatus, matched_fact_or_None, resolved_value_or_None)
    """
    if not facts:
        return QueryStatus.NOT_FOUND, None, None

    if len(facts) == 1:
        return QueryStatus.FOUND, facts[0], facts[0].value

    # Check if all facts carry identical values
    first_val = facts[0].value
    if all(f.value == first_val for f in facts):
        # Degenerate case: duplicate identical assertions -> not a true contradiction
        return QueryStatus.FOUND, facts[0], first_val

    # Multiple distinct values exist in active conflict
    if policy == ContradictionPolicy.DETERMINISTIC_ABSTAIN:
        return QueryStatus.CONTRADICTION, None, None

    elif policy == ContradictionPolicy.LAST_ASSERTION_WINS:
        # Sort key: asserted_at descending, then tie-break by fact.id ascending (deterministic)
        winner = sorted(facts, key=lambda f: (f.asserted_at, f.id), reverse=True)[0]
        # For equal asserted_at, we choose min(id) deterministically
        max_asserted = winner.asserted_at
        tied_by_time = [f for f in facts if f.asserted_at == max_asserted]
        if len(tied_by_time) > 1:
            winner = sorted(tied_by_time, key=lambda f: f.id)[0]
        return QueryStatus.FOUND, winner, winner.value

    elif policy == ContradictionPolicy.CONFIDENCE_WEIGHTED:
        # Highest confidence wins. Tie-breaks: latest asserted_at, then min(fact.id)
        max_conf = max(f.confidence for f in facts)
        tied_by_conf = [f for f in facts if abs(f.confidence - max_conf) < 1e-6]
        if len(tied_by_conf) == 1:
            winner = tied_by_conf[0]
        else:
            winner = sorted(tied_by_conf, key=lambda f: (f.asserted_at, f.id), reverse=True)[0]
            max_time = winner.asserted_at
            tied_by_time = [f for f in tied_by_conf if f.asserted_at == max_time]
            if len(tied_by_time) > 1:
                winner = sorted(tied_by_time, key=lambda f: f.id)[0]
        return QueryStatus.FOUND, winner, winner.value

    elif policy == ContradictionPolicy.MULTIVALUED_COLLECTION:
        # Collect and flatten all values, then return deterministic sorted list
        merged_values: List[Any] = []
        for f in facts:
            if isinstance(f.value, list):
                merged_values.extend(f.value)
            elif isinstance(f.value, (set, tuple)):
                merged_values.extend(list(f.value))
            else:
                merged_values.append(f.value)
        # Deduplicate and sort deterministically
        try:
            sorted_unique = sorted(list(set(merged_values)))
        except TypeError:
            # Fallback string representation sort if mixed types
            sorted_unique = sorted(list({str(v): v for v in merged_values}.values()), key=str)
        return QueryStatus.FOUND, None, sorted_unique

    raise ValueError(f"Unsupported contradiction policy: {policy}")


def apply_deletion(
    existing_facts: List[FactRecord], deletion: DeletionEvent
) -> List[FactRecord]:
    """Apply a deletion event according to its type and temporal scope.

    - FORWARD_ONLY:
      Preserves historical validity prior to effective_time.
      Facts encompassing effective_time are truncated to effective_time.
      Facts originating on or after effective_time are tombstoned or removed.
    - RETROACTIVE_PURGE:
      Expunges validity across past, present, and future.
      All matching facts are marked tombstoned (or removed).
    """
    modified: List[FactRecord] = []

    for fact in existing_facts:
        # Check entity and optional attribute filter
        if fact.entity_id != deletion.entity_id:
            modified.append(fact)
            continue
        if deletion.attribute is not None and fact.attribute != deletion.attribute:
            modified.append(fact)
            continue

        if deletion.deletion_scope == DeletionScope.RETROACTIVE_PURGE:
            if deletion.deletion_type == DeletionType.LOGICAL_TOMBSTONE:
                fact_dict = fact.model_dump()
                fact_dict["is_deleted"] = True
                fact_dict["deleted_at"] = deletion.asserted_at
                fact_dict["deletion_scope"] = DeletionScope.RETROACTIVE_PURGE
                modified.append(FactRecord(**fact_dict))
            elif deletion.deletion_type == DeletionType.PHYSICAL_PURGE:
                # Omit completely from list (physically purged)
                continue

        elif deletion.deletion_scope == DeletionScope.FORWARD_ONLY:
            # Historical fact strictly before deletion effective_time remains intact
            if fact.valid_to is not None and fact.valid_to <= deletion.effective_time:
                modified.append(fact)
            # Fact active across the deletion boundary is truncated
            elif fact.valid_from < deletion.effective_time:
                orig_valid_to = fact.valid_to
                fact_dict = fact.model_dump()
                fact_dict["valid_to"] = deletion.effective_time
                modified.append(FactRecord(**fact_dict))
                if deletion.deletion_type == DeletionType.LOGICAL_TOMBSTONE:
                    tombstone = FactRecord(
                        id=f"{fact.id}_tombstone",
                        entity_id=fact.entity_id,
                        attribute=fact.attribute,
                        value=fact.value,
                        valid_from=deletion.effective_time,
                        valid_to=orig_valid_to,
                        asserted_at=deletion.asserted_at,
                        is_deleted=True,
                        deleted_at=deletion.asserted_at,
                        deletion_scope=DeletionScope.FORWARD_ONLY,
                    )
                    modified.append(tombstone)
            # Fact starting at or after deletion effective_time is deleted
            else:
                if deletion.deletion_type == DeletionType.LOGICAL_TOMBSTONE:
                    fact_dict = fact.model_dump()
                    fact_dict["is_deleted"] = True
                    fact_dict["deleted_at"] = deletion.asserted_at
                    fact_dict["deletion_scope"] = DeletionScope.FORWARD_ONLY
                    modified.append(FactRecord(**fact_dict))
                elif deletion.deletion_type == DeletionType.PHYSICAL_PURGE:
                    continue

    return modified


def evaluate_query_against_facts(
    facts: List[FactRecord],
    query: MemoryQuery,
    contradiction_policy: ContradictionPolicy = ContradictionPolicy.DETERMINISTIC_ABSTAIN,
) -> QueryPrediction:
    """Evaluate a MemoryQuery against a collection of FactRecords in pure domain logic."""
    # 1. Match entity and attribute
    candidates = [
        f for f in facts
        if f.entity_id == query.entity_id and f.attribute == query.attribute
    ]

    if not candidates:
        return QueryPrediction(
            query_id=query.query_id,
            status=QueryStatus.NOT_FOUND,
            value=None,
            matched_entity_id=None,
            fact_id=None,
        )

    # 2. Filter by assertion time (if None, use current assertion time: unretracted assertions only)
    if query.as_of_assertion_time is not None:
        t_a = query.as_of_assertion_time
        candidates = [
            f for f in candidates
            if f.asserted_at <= t_a and (f.retracted_at is None or t_a < f.retracted_at)
        ]
    else:
        candidates = [
            f for f in candidates
            if f.retracted_at is None
        ]

    # 3. Check for retroactive tombstone purge effective as of query assertion time
    retroactive_tombstones = [
        f for f in candidates
        if f.is_deleted
        and f.deletion_scope == DeletionScope.RETROACTIVE_PURGE
        and (
            query.as_of_assertion_time is None
            or f.deleted_at is None
            or f.deleted_at <= query.as_of_assertion_time
        )
    ]
    if retroactive_tombstones and not query.include_tombstones:
        return QueryPrediction(
            query_id=query.query_id,
            status=QueryStatus.TOMBSTONED_DELETED,
            value=None,
            matched_entity_id=query.entity_id,
            fact_id=retroactive_tombstones[0].id,
            diagnostic_info="Record under retroactive deletion purge",
        )

    # 4. Filter by valid time
    if query.as_of_valid_time is not None:
        t_v = query.as_of_valid_time
        valid_candidates = [
            f for f in candidates
            if is_point_in_interval(t_v, f.valid_from, f.valid_to)
        ]
    else:
        # Open-ended current facts
        valid_candidates = [
            f for f in candidates
            if f.valid_to is None
        ]

    # 5. Handle deletion masking on valid candidates
    active_candidates: List[FactRecord] = []
    has_tombstone = False
    tombstone_id = None

    for f in valid_candidates:
        is_deleted_effective = (
            f.is_deleted
            and (
                query.as_of_assertion_time is None
                or f.deleted_at is None
                or f.deleted_at <= query.as_of_assertion_time
            )
        )
        if is_deleted_effective:
            has_tombstone = True
            tombstone_id = f.id
            if query.include_tombstones:
                active_candidates.append(f)
        else:
            active_candidates.append(f)

    if has_tombstone and not query.include_tombstones and not active_candidates:
        return QueryPrediction(
            query_id=query.query_id,
            status=QueryStatus.TOMBSTONED_DELETED,
            value=None,
            matched_entity_id=query.entity_id,
            fact_id=tombstone_id,
            diagnostic_info="Fact masked by logical tombstone",
        )

    if not active_candidates:
        # A fact is superseded/stale ONLY IF it existed and expired historically prior to query valid time
        historical_superseded = [
            f for f in candidates
            if not (
                f.is_deleted
                and (
                    query.as_of_assertion_time is None
                    or f.deleted_at is None
                    or f.deleted_at <= query.as_of_assertion_time
                )
            )
            and f.valid_to is not None
            and query.as_of_valid_time is not None
            and f.valid_to <= query.as_of_valid_time
        ]
        if historical_superseded:
            return QueryPrediction(
                query_id=query.query_id,
                status=QueryStatus.SUPERSEDED_STALE,
                value=None,
                matched_entity_id=query.entity_id,
                diagnostic_info="No fact valid at specified coordinates, but historical facts exist",
            )
        return QueryPrediction(
            query_id=query.query_id,
            status=QueryStatus.NOT_FOUND,
            value=None,
            matched_entity_id=None,
        )

    # 6. Resolve contradiction among active valid candidates
    effective_policy = query.contradiction_policy or contradiction_policy
    status, matched_fact, resolved_value = resolve_contradiction(
        active_candidates, effective_policy
    )

    return QueryPrediction(
        query_id=query.query_id,
        status=status,
        value=resolved_value,
        matched_entity_id=matched_fact.entity_id if matched_fact else (query.entity_id if status == QueryStatus.FOUND else None),
        fact_id=matched_fact.id if matched_fact else None,
        valid_interval=[matched_fact.valid_from, matched_fact.valid_to] if matched_fact else None,
    )
