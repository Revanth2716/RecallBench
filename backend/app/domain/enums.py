"""RecallBench domain enums for temporal memory evaluation."""
from enum import Enum


class UpdatePolicy(str, Enum):
    """Semantics applied when an update event modifies an existing entity attribute."""
    UPSERT_OVERWRITE = "UPSERT_OVERWRITE"          # Overwrite value immediately without preserving historical interval
    TEMPORAL_SUPERSEDE = "TEMPORAL_SUPERSEDE"      # Terminate interval of prior fact and open new valid interval
    REJECT_IF_CONFLICT = "REJECT_IF_CONFLICT"      # Reject update if an active conflicting record exists
    BRANCH_MULTI_VALUED = "BRANCH_MULTI_VALUED"    # Permit multiple active coexisting values


class ContradictionPolicy(str, Enum):
    """Explicit policy used to resolve conflicting facts with overlapping valid intervals."""
    DETERMINISTIC_ABSTAIN = "DETERMINISTIC_ABSTAIN"  # Return CONTRADICTION status with no value
    LAST_ASSERTION_WINS = "LAST_ASSERTION_WINS"      # Select fact with the latest asserted_at timestamp
    CONFIDENCE_WEIGHTED = "CONFIDENCE_WEIGHTED"      # Select fact with highest confidence score
    MULTIVALUED_COLLECTION = "MULTIVALUED_COLLECTION"# Merge distinct values into a sorted list


class DeletionType(str, Enum):
    """Persistence mechanism for deleted records."""
    LOGICAL_TOMBSTONE = "LOGICAL_TOMBSTONE"  # Preserve record marked as tombstone; excluded from normal retrieval
    PHYSICAL_PURGE = "PHYSICAL_PURGE"        # Remove row from storage table (operational deletion)


class DeletionScope(str, Enum):
    """Temporal reach of a deletion event."""
    FORWARD_ONLY = "FORWARD_ONLY"            # Invalidates validity from deletion effective_time onwards
    RETROACTIVE_PURGE = "RETROACTIVE_PURGE"  # Expunges all validity across past, present, and future


class QueryStatus(str, Enum):
    """Status returned by a memory query."""
    FOUND = "FOUND"                          # Active fact found matching query coordinates
    NOT_FOUND = "NOT_FOUND"                  # No fact exists for entity/attribute at query coordinates
    SUPERSEDED_STALE = "SUPERSEDED_STALE"    # Fact exists historically but is superseded at query coordinates
    TOMBSTONED_DELETED = "TOMBSTONED_DELETED"# Fact was explicitly deleted prior to or covering query coordinates
    CONTRADICTION = "CONTRADICTION"          # Multiple conflicting active facts exist under ABSTAIN policy


class BenchmarkCategory(str, Enum):
    """RecallBench benchmark categories."""
    TEMPORAL_RECALL = "TEMPORAL_RECALL"
    STALE_FACT_DETECTION = "STALE_FACT_DETECTION"
    CONTRADICTION_HANDLING = "CONTRADICTION_HANDLING"
    ENTITY_ISOLATION = "ENTITY_ISOLATION"
    DELETION_COMPLIANCE = "DELETION_COMPLIANCE"
