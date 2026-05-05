"""Lightweight worker-agent records layered on top of DAG execution.

This module does not implement a full multi-agent system. It introduces
just enough structure to make the worker responsible for a node explicit:

- each node attempt gets a worker-agent identity
- the worker-agent has a small lifecycle record
- the lifecycle can later evolve into a richer subagent runtime
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from taskcall_perception_map.domain.models import utc_timestamp


WorkerAgentStatus = Literal["spawned", "running", "success", "failed", "partial"]


@dataclass(slots=True)
class WorkerAgentIdentity:
    """Stable identity for the worker assigned to one node attempt."""

    agent_id: str
    session_id: str
    node_id: str
    agent_profile: str
    attempt_count: int
    display_name: str
    parent_agent_id: str | None = None


@dataclass(slots=True)
class WorkerAgentSession:
    """Lifecycle record for one lightweight worker-agent run."""

    identity: WorkerAgentIdentity
    status: WorkerAgentStatus = "spawned"
    transcript_id: str | None = None
    produced_artifact_fields: list[str] = field(default_factory=list)
    last_error: str | None = None
    created_at: str = field(default_factory=utc_timestamp)
    started_at: str | None = None
    finished_at: str | None = None
