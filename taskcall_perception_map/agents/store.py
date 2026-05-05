"""In-memory storage for lightweight worker-agent lifecycle records."""

from __future__ import annotations

from copy import deepcopy

from taskcall_perception_map.agents.models import WorkerAgentSession


class InMemoryWorkerAgentStore:
    """Persist worker-agent sessions so execution ownership is inspectable."""

    def __init__(self) -> None:
        self._sessions: dict[str, WorkerAgentSession] = {}

    def put(self, session: WorkerAgentSession) -> None:
        self._sessions[session.identity.agent_id] = deepcopy(session)

    def get(self, agent_id: str) -> WorkerAgentSession:
        return deepcopy(self._sessions[agent_id])

    def update(self, session: WorkerAgentSession) -> None:
        self._sessions[session.identity.agent_id] = deepcopy(session)

    def list_all(self) -> list[WorkerAgentSession]:
        return [deepcopy(session) for session in self._sessions.values()]

    def list_by_session(self, session_id: str) -> list[WorkerAgentSession]:
        return [
            deepcopy(session)
            for session in self._sessions.values()
            if session.identity.session_id == session_id
        ]

    def list_by_node(self, node_id: str) -> list[WorkerAgentSession]:
        return [
            deepcopy(session)
            for session in self._sessions.values()
            if session.identity.node_id == node_id
        ]
