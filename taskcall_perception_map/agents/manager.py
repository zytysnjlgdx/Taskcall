"""Worker Agent 管理器：为每个节点执行分配和追踪 worker agent。"""

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

# WorkerAgentFactory: 工厂函数，接收 (task_package, identity) 返回一个 WorkerAgent
WorkerAgentFactory = Callable[[RuntimeTaskPackage, WorkerAgentIdentity], WorkerAgent]

# ParentAgentResolver: 解析父 agent id 的函数，用于 agent 层级关系
ParentAgentResolver = Callable[[RuntimeTaskPackage], str | None]


class WorkerAgentManager:
    """
    Worker Agent 管理器：为每个节点的每次执行创建和追踪一个 worker agent。

    作用：
        - 为每次节点执行创建一个唯一的 agent 身份（WorkerAgentIdentity）
        - 追踪 agent 的生命周期（创建 → running → 成功/失败）
        - 把执行结果（NodeExecutionResult）记录回 agent 的生命周期档案
    """

    def __init__(
        self,
        *,
        worker_agent_factory: WorkerAgentFactory,
        agent_store: InMemoryWorkerAgentStore,
        parent_agent_resolver: ParentAgentResolver | None = None,
    ) -> None:
        """
        初始化 agent 管理器。

        参数:
            worker_agent_factory: 工厂函数，用于创建 WorkerAgent 实例
            agent_store: agent 会话存储（内存级）
            parent_agent_resolver: 可选，解析父 agent id 的函数
        """
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
        """
        为一个节点执行创建一个 worker agent：生成身份 → 存储 → 构建 agent 实例。

        输入:
            task_package: 该节点的执行包（RuntimeTaskPackage）
            attempt_count: 当前是第几次尝试（重试时 > 1）

        输出:
            WorkerAgent: 创建好的 worker agent 实例
        """
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
        """
        标记 agent 为 running 状态，记录开始时间。

        输入:
            agent_id: agent 唯一标识
        """
        session = self.agent_store.get(agent_id)
        session.status = "running"
        session.started_at = utc_timestamp()
        self.agent_store.update(session)

    def finalize(self, agent_id: str, result: NodeExecutionResult) -> None:
        """
        把节点执行结果写回 agent 生命周期档案。

        输入:
            agent_id: agent 唯一标识
            result: 节点执行结果（NodeExecutionResult）
        """
        session = self.agent_store.get(agent_id)
        session.status = result.status
        session.transcript_id = result.transcript_id
        session.produced_artifact_fields = [artifact.field for artifact in result.artifacts]
        session.last_error = result.failure_reason
        session.finished_at = utc_timestamp()
        self.agent_store.update(session)

    def mark_failed(self, agent_id: str, reason: str) -> None:
        """
        标记 agent 为 failed 状态，记录失败原因。

        输入:
            agent_id: agent 唯一标识
            reason: 失败原因描述
        """
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
        """
        构建 agent 的可读显示名称，格式为 "agent_profile:node_id:attempt-N"。

        输入:
            task_package: 执行包
            attempt_count: 尝试次数

        输出:
            str: 可读名称，如 "general_worker:q2:attempt-1"
        """
        return (
            f"{task_package.agent_profile}"
            f":{task_package.node_id}"
            f":attempt-{attempt_count}"
        )
