"""节点执行封装层：把一个 PlanNode 变成一次具体的 agent 执行。"""

from __future__ import annotations

from taskcall_perception_map.agents.manager import WorkerAgentManager
from taskcall_perception_map.domain.models import NodeExecutionResult, PlanGraph, PlanNode
from taskcall_perception_map.runtime.loop_engine import LoopEngine
from taskcall_perception_map.runtime.task_package_builder import TaskPackageBuilder
from taskcall_perception_map.storage.artifact_store import InMemoryArtifactStore


class NodeRunner:
    """
    节点执行器：接收一个 PlanNode，组装执行包，分配 agent，执行，返回结果。

    在调度器（scheduler）和执行引擎（loop_engine）之间起到桥梁作用：
    - 调度器只管"下一个该跑哪个节点"
    - NodeRunner 负责"怎么跑这个节点"
    """

    def __init__(
        self,
        *,
        task_package_builder: TaskPackageBuilder,
        loop_engine: LoopEngine,
        worker_agent_manager: WorkerAgentManager,
    ) -> None:
        """
        初始化节点执行器。

        参数:
            task_package_builder: 把 PlanNode + 上游产物组装成 RuntimeTaskPackage
            loop_engine: 执行引擎，驱动 agent 完成单个子任务
            worker_agent_manager: agent 管理器，负责分配、标记状态、收集结果
        """
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
        """
        执行单个节点：组装执行包 → 分配 agent → 执行 → 返回结果。

        输入:
            session_id: 当前会话 id
            plan: 完整的 PlanGraph（用于取 question_text 等全局信息）
            node: 要执行的 PlanNode
            artifact_store: 产物仓库（用于解析 upstream_inputs）
            attempt_count: 当前是第几次尝试（重试时 > 1）

        输出:
            NodeExecutionResult: 执行结果（成功时包含 artifacts，失败时包含 error）
        """
        # 1. 把 PlanNode + 上游产物组装成可执行的 RuntimeTaskPackage
        task_package = self.task_package_builder.build(
            session_id=session_id,
            question_text=plan.question_text,
            node=node,
            artifact_store=artifact_store,
        )

        # 2. 分配一个 worker agent 来执行这个节点
        worker_agent = self.worker_agent_manager.spawn_for_node(
            task_package=task_package,
            attempt_count=attempt_count,
        )

        # 把 agent 信息记到 metadata 里，方便调试追踪
        task_package.metadata["worker_agent_id"] = worker_agent.identity.agent_id
        task_package.metadata["worker_agent_name"] = worker_agent.identity.display_name

        # 3. 标记 agent 为 running，然后执行
        self.worker_agent_manager.mark_running(worker_agent.identity.agent_id)
        try:
            result = await self.loop_engine.run(
                task_package=task_package,
                adapter=worker_agent,
                attempt_count=attempt_count,
            )
        except Exception as exc:
            # 执行异常，标记 agent 为 failed
            self.worker_agent_manager.mark_failed(
                worker_agent.identity.agent_id,
                str(exc),
            )
            raise

        # 4. 执行完成，记录结果 
        self.worker_agent_manager.finalize(worker_agent.identity.agent_id, result)
        return result
