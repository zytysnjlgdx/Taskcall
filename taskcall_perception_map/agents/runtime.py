"""Runtime for synchronous child worker-agent delegation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from taskcall_perception_map.agents.manager import WorkerAgentManager
from taskcall_perception_map.agents.models import WorkerAgentIdentity, WorkerAgentStatus
from taskcall_perception_map.agents.registry import AgentRegistry
from taskcall_perception_map.domain.models import (
    RuntimeTaskPackage,
    SemanticArtifact,
    SpawnAgentStep,
)
from taskcall_perception_map.runtime.loop_engine import LoopEngine


@dataclass(slots=True)
class AgentResult:
    """Normalized child-agent result returned to the parent loop."""

    identity: WorkerAgentIdentity
    status: WorkerAgentStatus
    artifacts: list[SemanticArtifact]
    transcript_id: str
    raw_output: Any | None = None
    failure_reason: str | None = None


class ChildAgentRuntime(Protocol):
    """Run one child-agent request and return its normalized result."""

    async def run_child_agent(
        self,
        *,
        parent_task_package: RuntimeTaskPackage,
        parent_transcript_id: str,
        parent_iteration: int,
        step: SpawnAgentStep,
    ) -> AgentResult:
        ...


class NestedAgentRuntime:
    """Resolve, spawn, and execute one child worker-agent synchronously."""

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry,
        worker_agent_manager: WorkerAgentManager,
        loop_engine: LoopEngine,
    ) -> None:
        self.agent_registry = agent_registry
        self.worker_agent_manager = worker_agent_manager
        self.loop_engine = loop_engine

    async def run_child_agent(
        self,
        *,
        parent_task_package: RuntimeTaskPackage,
        parent_transcript_id: str,
        parent_iteration: int,
        step: SpawnAgentStep,
    ) -> AgentResult:
        definition = self.agent_registry.select(
            task_goal=step.task_goal,
            requested_agent_type=step.requested_agent_type,
            required_capabilities=step.required_capabilities,
        )
        task_package = self._build_child_task_package(
            parent_task_package=parent_task_package,
            parent_transcript_id=parent_transcript_id,
            parent_iteration=parent_iteration,
            step=step,
            selected_agent_type=definition.agent_type,
            supported_capabilities=definition.supported_capabilities,
            default_instruction=definition.default_instruction,
        )

        worker_agent = self.worker_agent_manager.spawn_for_node(
            task_package=task_package,
            attempt_count=1,
        )
        task_package.metadata["worker_agent_id"] = worker_agent.identity.agent_id
        task_package.metadata["worker_agent_name"] = worker_agent.identity.display_name

        self.worker_agent_manager.mark_running(worker_agent.identity.agent_id)
        try:
            result = await self.loop_engine.run(
                task_package=task_package,
                adapter=worker_agent,
                attempt_count=1,
            )
        except Exception as exc:
            self.worker_agent_manager.mark_failed(
                worker_agent.identity.agent_id,
                str(exc),
            )
            raise

        self.worker_agent_manager.finalize(worker_agent.identity.agent_id, result)
        return AgentResult(
            identity=worker_agent.identity,
            status=result.status,
            artifacts=result.artifacts,
            transcript_id=result.transcript_id,
            raw_output=result.raw_output,
            failure_reason=result.failure_reason,
        )

    def _build_child_task_package(
        self,
        *,
        parent_task_package: RuntimeTaskPackage,
        parent_transcript_id: str,
        parent_iteration: int,
        step: SpawnAgentStep,
        selected_agent_type: str,
        supported_capabilities: list[str],
        default_instruction: str | None,
    ) -> RuntimeTaskPackage:
        metadata = dict(step.metadata)
        metadata["parent_agent_id"] = parent_task_package.metadata.get(
            "worker_agent_id"
        )
        metadata["parent_agent_name"] = parent_task_package.metadata.get(
            "worker_agent_name"
        )
        metadata["parent_node_id"] = parent_task_package.node_id
        metadata["parent_transcript_id"] = parent_transcript_id
        metadata["selected_agent_type"] = selected_agent_type
        metadata["requested_agent_type"] = step.requested_agent_type

        allowed_capabilities = (
            list(step.required_capabilities)
            if step.required_capabilities
            else list(supported_capabilities)
        )
        local_evidence = (
            list(step.local_evidence)
            if step.local_evidence
            else list(parent_task_package.local_evidence)
        )
        instruction = step.instruction or default_instruction or (
            f"Complete delegated task for parent node "
            f"{parent_task_package.node_id}: {step.task_goal}"
        )

        return RuntimeTaskPackage(
            session_id=parent_task_package.session_id,
            question_text=parent_task_package.question_text,
            node_id=self._build_child_node_id(
                parent_task_package=parent_task_package,
                parent_iteration=parent_iteration,
                step=step,
                selected_agent_type=selected_agent_type,
            ),
            goal=step.task_goal,
            agent_profile=selected_agent_type,
            local_evidence=local_evidence,
            upstream_inputs=list(step.provided_inputs),
            expected_outputs=list(step.expected_outputs),
            instruction=instruction,
            allowed_capabilities=allowed_capabilities,
            metadata=metadata,
        )

    @staticmethod
    def _build_child_node_id(
        *,
        parent_task_package: RuntimeTaskPackage,
        parent_iteration: int,
        step: SpawnAgentStep,
        selected_agent_type: str,
    ) -> str:
        alias = step.save_as or selected_agent_type
        return (
            f"{parent_task_package.node_id}"
            f"::child::{NestedAgentRuntime._sanitize(alias)}"
            f"::iter-{parent_iteration}"
        )

    @staticmethod
    def _sanitize(value: str) -> str:
        return "".join(
            character if character.isalnum() or character in {"_", "-"} else "_"
            for character in value
        )
