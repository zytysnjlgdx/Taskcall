"""Minimal manager that assigns explicit worker-agents to DAG nodes."""

from __future__ import annotations

from typing import Callable
from uuid import uuid4

from taskcall_perception_map.agents.base import WorkerAgent
from taskcall_perception_map.agents.models import WorkerAgentIdentity, WorkerAgentSession
from taskcall_perception_map.agents.store import InMemoryWorkerAgentStore
from taskcall_perception_map.domain.models import (
    NodeExecutionResult,
    RuntimeTaskPackage,
    utc_timestamp,
)


WorkerAgentFactory = Callable[[RuntimeTaskPackage, WorkerAgentIdentity], WorkerAgent]
ParentAgentResolver = Callable[[RuntimeTaskPackage], str | None]


class WorkerAgentManager:
    """Create and track one worker-agent per node execution attempt."""

    def __init__(
        self,
        *,
        worker_agent_factory: WorkerAgentFactory,
        agent_store: InMemoryWorkerAgentStore,
        parent_agent_resolver: ParentAgentResolver | None = None,
    ) -> None:
        self.worker_agent_factory = worker_agent_factory
        self.agent_store = agent_store
        self.parent_agent_resolver = parent_agent_resolver or (
            lambda task_package: task_package.metadata.get("parent_agent_id")
        )

    def spawn_for_node(
        self,
        *,
        task_package: RuntimeTaskPackage,
        attempt_count: int,
    ) -> WorkerAgent:
        """Create a worker-agent identity, persist it, and build the worker."""
        identity = WorkerAgentIdentity(
            agent_id=str(uuid4()),
            session_id=task_package.session_id,
            node_id=task_package.node_id,
            agent_profile=task_package.agent_profile,
            attempt_count=attempt_count,
            display_name=self._build_display_name(task_package, attempt_count),
            parent_agent_id=self.parent_agent_resolver(task_package),
        )
        self.agent_store.put(WorkerAgentSession(identity=identity))
        return self.worker_agent_factory(task_package, identity)

    def mark_running(self, agent_id: str) -> None:
        session = self.agent_store.get(agent_id)
        session.status = "running"
        session.started_at = utc_timestamp()
        self.agent_store.update(session)

    def finalize(self, agent_id: str, result: NodeExecutionResult) -> None:
        """Fold a node result back into the worker-agent lifecycle record."""
        session = self.agent_store.get(agent_id)
        session.status = result.status
        session.transcript_id = result.transcript_id
        session.produced_artifact_fields = [artifact.field for artifact in result.artifacts]
        session.last_error = result.failure_reason
        session.finished_at = utc_timestamp()
        self.agent_store.update(session)

    def mark_failed(self, agent_id: str, reason: str) -> None:
        session = self.agent_store.get(agent_id)
        session.status = "failed"
        session.last_error = reason
        session.finished_at = utc_timestamp()
        self.agent_store.update(session)

    @staticmethod
    def _build_display_name(
        task_package: RuntimeTaskPackage,
        attempt_count: int,
    ) -> str:
        return (
            f"{task_package.agent_profile}"
            f":{task_package.node_id}"
            f":attempt-{attempt_count}"
        )
