"""In-memory transcript storage for node-by-node execution logs."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from taskcall_perception_map.domain.models import (
    TranscriptEntry,
    TranscriptRecord,
    utc_timestamp,
)


class InMemoryTranscriptStore:
    """Store append-only records that explain how a node reached a result."""

    def __init__(self) -> None:
        self._records: dict[str, TranscriptRecord] = {}

    def create(self, node_id: str) -> TranscriptRecord:
        """Start a new transcript for one node execution."""
        transcript_id = str(uuid4())
        record = TranscriptRecord(transcript_id=transcript_id, node_id=node_id)
        self._records[transcript_id] = record
        return deepcopy(record)

    def append(self, transcript_id: str, entry: TranscriptEntry) -> None:
        """Append one event and refresh the transcript timestamp."""
        record = self._records[transcript_id]
        record.entries.append(deepcopy(entry))
        record.updated_at = utc_timestamp()

    def get(self, transcript_id: str) -> TranscriptRecord:
        """Read back the full transcript for one node."""
        return deepcopy(self._records[transcript_id])

    def list_all(self) -> list[TranscriptRecord]:
        """Return all transcripts captured so far."""
        return [deepcopy(record) for record in self._records.values()]
