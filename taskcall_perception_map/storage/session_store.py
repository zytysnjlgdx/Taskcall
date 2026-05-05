"""In-memory scheduler snapshot storage.

The session store tracks the global state of a run: node statuses,
the original plan, and the accumulated artifacts visible to the
scheduler.
"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from taskcall_perception_map.domain.models import (
    NodeRuntimeState,
    PlanGraph,
    SemanticArtifact,
    SessionSnapshot,
    utc_timestamp,
)


def create_initial_node_states(plan: PlanGraph) -> dict[str, NodeRuntimeState]:
    """Seed every node as pending before dependency resolution begins."""
    return {
        node.id: NodeRuntimeState(node_id=node.id)
        for node in plan.nodes
    }


class InMemorySessionStore:
    """Store and clone scheduler snapshots so callers cannot mutate state."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionSnapshot] = {}

    def create(self, plan: PlanGraph, session_id: str | None = None) -> SessionSnapshot:
        """Create a new run session and return a defensive copy."""
        resolved_session_id = session_id or str(uuid4())
        snapshot = SessionSnapshot(
            session_id=resolved_session_id,
            plan=plan,
            node_states=create_initial_node_states(plan),
        )
        self._sessions[resolved_session_id] = snapshot
        return deepcopy(snapshot)

    def get(self, session_id: str) -> SessionSnapshot:
        """Read the latest snapshot for one session."""
        snapshot = self._sessions[session_id]
        return deepcopy(snapshot)

    def update_node_state(self, session_id: str, state: NodeRuntimeState) -> None:
        """Replace one node state and refresh the snapshot timestamp."""
        snapshot = self._sessions[session_id]
        snapshot.node_states[state.node_id] = deepcopy(state)
        snapshot.updated_at = utc_timestamp()

    def replace_artifacts(
        self,
        session_id: str,
        artifacts: list[SemanticArtifact],
    ) -> None:
        """Replace the artifact view stored inside the session snapshot."""
        snapshot = self._sessions[session_id]
        snapshot.artifacts = deepcopy(artifacts)
        snapshot.updated_at = utc_timestamp()

    def list_sessions(self) -> list[SessionSnapshot]:
        """Return copies of every known session snapshot."""
        return [deepcopy(snapshot) for snapshot in self._sessions.values()]
