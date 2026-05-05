"""Node execution wrapper.

This layer keeps the DAG scheduler unchanged while making the node
executor more explicit: each node attempt is assigned to a lightweight
worker-agent before entering the loop engine.
"""

from __future__ import annotations

from taskcall_perception_map.agents.manager import WorkerAgentManager
from taskcall_perception_map.domain.models import NodeExecutionResult, PlanGraph, PlanNode
from taskcall_perception_map.runtime.loop_engine import LoopEngine
from taskcall_perception_map.runtime.task_package_builder import TaskPackageBuilder
from taskcall_perception_map.storage.artifact_store import InMemoryArtifactStore


class NodeRunner:
    """Turn one plan node into one concrete worker-agent execution attempt."""

    def __init__(
        self,
        *,
        task_package_builder: TaskPackageBuilder,
        loop_engine: LoopEngine,
        worker_agent_manager: WorkerAgentManager,
    ) -> None:
        self.task_package_builder = task_package_builder
        self.loop_engine = loop_engine
        self.worker_agent_manager = worker_agent_manager

    async def run_node(
        self,
        *,
        session_id: str,
        plan: PlanGraph,
        node: PlanNode,
        artifact_store: InMemoryArtifactStore,
        attempt_count: int,
    ) -> NodeExecutionResult:
        # Build the fully resolved task package before choosing the worker.
        task_package = self.task_package_builder.build(
            session_id=session_id,
            question_text=plan.question_text,
            node=node,
            artifact_store=artifact_store,
        )
        worker_agent = self.worker_agent_manager.spawn_for_node(
            task_package=task_package,
            attempt_count=attempt_count,
        )

        # Stamp the assigned worker onto metadata so transcript and later
        # orchestration layers can inspect who executed this node.
        task_package.metadata["worker_agent_id"] = worker_agent.identity.agent_id
        task_package.metadata["worker_agent_name"] = worker_agent.identity.display_name

        self.worker_agent_manager.mark_running(worker_agent.identity.agent_id)
        try:
            result = await self.loop_engine.run(
                task_package=task_package,
                adapter=worker_agent,
                attempt_count=attempt_count,
            )
        except Exception as exc:
            self.worker_agent_manager.mark_failed(
                worker_agent.identity.agent_id,
                str(exc),
            )
            raise

        self.worker_agent_manager.finalize(worker_agent.identity.agent_id, result)
        return result
