"""Protocols and adapter contracts for target memory stores.

Enforces strict black-box isolation: the evaluation engine only interacts
with implementations of MemoryStoreAdapter through its retrieve and ingest APIs.
"""
from typing import Any, Dict, Protocol, runtime_checkable

from .models import MemoryQuery, QueryPrediction


@runtime_checkable
class MemoryStoreAdapter(Protocol):
    """Black-box adapter contract for memory systems under test."""

    def reset(self) -> None:
        """Reset all internal state to empty before executing a benchmark scenario."""
        ...

    def ingest_event(self, event: Dict[str, Any]) -> None:
        """Ingest a timeline event (insert, update, delete)."""
        ...

    def retrieve(self, query: MemoryQuery) -> QueryPrediction:
        """Execute a black-box retrieval query.

        Returns only a QueryPrediction DTO; never exposes internal database
        handles, table names, or raw cursors to the caller.
        """
        ...
