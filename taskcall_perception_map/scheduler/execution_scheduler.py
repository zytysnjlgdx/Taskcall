"""全局调度器。

这个文件回答的问题是：
“当一张 PlanGraph 已经准备好之后，系统怎么一步一步把它跑完？”

它只关心全局推进，不关心单个节点内部怎么思考。
也就是说：
- 节点之间谁先跑、谁后跑，归它管
- 节点内部怎么循环、怎么调工具，不归它管

整体职责：
1. 创建 session
2. 找到依赖已满足的 ready 节点
3. 按批次并发执行这些节点
4. 接收结果并更新全局状态
5. 根据结果决定成功、失败或重试
6. 直到没有任何节点还能继续推进
"""

from __future__ import annotations

import asyncio

from taskcall_perception_map.domain.models import (
    NodeExecutionResult,
    NodeRuntimeState,
    PlanGraph,
    SchedulerRunSummary,
    utc_timestamp,
)
from taskcall_perception_map.runtime.node_runner import NodeRunner
from taskcall_perception_map.scheduler.dependencies import get_ready_node_ids, sync_ready_states
from taskcall_perception_map.scheduler.retry_policy import FixedRetryPolicy, RetryPolicy
from taskcall_perception_map.storage.artifact_store import InMemoryArtifactStore
from taskcall_perception_map.storage.session_store import InMemorySessionStore


def batched(items: list[str], batch_size: int) -> list[list[str]]:
    """把 ready 节点切成多个批次。

    这样做的目的是限制并发度，避免一次把所有 ready 节点全部放出去。
    """
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


class ExecutionScheduler:
    """驱动整张 DAG 一直运行到不能再推进为止。"""

    def __init__(
        self,
        *,
        node_runner: NodeRunner,  # runtime 层的组件，负责执行单个节点
        artifact_store: InMemoryArtifactStore,
        session_store: InMemorySessionStore,
        retry_policy: RetryPolicy | None = None,
        max_parallel: int = 2,
    ) -> None:
        self.node_runner = node_runner
        self.artifact_store = artifact_store
        self.session_store = session_store
        self.retry_policy = retry_policy or FixedRetryPolicy()
        self.max_parallel = max(1, max_parallel)

    async def run(
        self,
        plan: PlanGraph,
        *,
        session_id: str | None = None,
    ) -> SchedulerRunSummary:
        # 一次 run 对应一个 session。后面所有 node state 和 artifacts
        # 都会沉淀到这个 session snapshot 里。
        snapshot = self.session_store.create(plan, session_id=session_id)  # 给一道题创建一个session

        while True:
            current_snapshot = self.session_store.get(snapshot.session_id)
            # 每轮开始前，先根据依赖关系刷新 ready 状态。
            # 例如：如果 A、B 都成功了，那么依赖 A、B 的 C 就可以从
            # pending 变成 ready。
            sync_ready_states(plan, current_snapshot.node_states)  # 把可执行的节点status设置为ready
            for state in current_snapshot.node_states.values():  # 更新快照中记录的节点状态
                self.session_store.update_node_state(snapshot.session_id, state)

            ready_node_ids = get_ready_node_ids(plan, current_snapshot.node_states)
            if not ready_node_ids:
                # 没有 ready 节点就说明调度器已经无法继续推进。
                # 可能是全完成，也可能是某些节点失败导致后继永远卡住。
                break

            # 同一批里的节点可以并发执行，因为它们此刻都已经满足依赖条件。
            for batch in batched(ready_node_ids, self.max_parallel):
                await asyncio.gather(
                    *[
                        self._execute_node(
                            session_id=snapshot.session_id,
                            plan=plan,
                            node_id=node_id,
                        )
                        for node_id in batch
                    ]
                )

        final_snapshot = self.session_store.get(snapshot.session_id)
        completed_node_ids = [
            node_id
            for node_id, state in final_snapshot.node_states.items()
            if state.status == "success"
        ]
        failed_node_ids = [
            node_id
            for node_id, state in final_snapshot.node_states.items()
            if state.status == "failed"
        ]
        pending_node_ids = [
            node_id
            for node_id, state in final_snapshot.node_states.items()
            if state.status in {"pending", "ready", "running"}
        ]

        return SchedulerRunSummary(
            session_id=snapshot.session_id,
            completed_node_ids=completed_node_ids,
            failed_node_ids=failed_node_ids,
            pending_node_ids=pending_node_ids,
            artifacts=self.artifact_store.list_all(),
            snapshot=final_snapshot,
        )

    async def _execute_node(
        self,
        *,
        session_id: str,
        plan: PlanGraph,
        node_id: str,
    ) -> None:
        # 这里做的是“单节点的一次调度尝试”，不是整个 session 的运行。
        snapshot = self.session_store.get(session_id)
        node = next(node for node in plan.nodes if node.id == node_id)  # 在 plan.nodes 里面找到第一个 id == node_id 的节点，并把它赋值给 node
        state = snapshot.node_states[node_id]

        # 先把节点状态切到 running，再真正交给 runtime。
        running_state = NodeRuntimeState(
            node_id=node_id,
            status="running",
            attempt_count=state.attempt_count + 1,
            last_error=None,
            started_at=utc_timestamp(),
            finished_at=None,
        )
        self.session_store.update_node_state(session_id, running_state)

        try:
            result = await self.node_runner.run_node(
                session_id=session_id,
                plan=plan,
                node=node,
                artifact_store=self.artifact_store,
                attempt_count=running_state.attempt_count,
            )
        except Exception as exc:  # noqa: BLE001
            result = NodeExecutionResult(
                node_id=node_id,
                status="failed",
                artifacts=[],
                transcript_id="builder-error",
                failure_reason=str(exc),
                retryable=False,
            )

        # 把节点执行结果重新折叠回 scheduler 的全局状态里。
        self._apply_result(session_id=session_id, prior_state=running_state, result=result)

    def _apply_result(
        self,
        *,
        session_id: str,
        prior_state: NodeRuntimeState,
        result: NodeExecutionResult,
    ) -> None:
        if result.status == "success":
            # 一旦成功，这个节点产出的 artifacts 就会进入全局 artifact store，
            # 后继节点后面就能引用这些结果了。
            self.artifact_store.put_many(result.artifacts)
            self.session_store.replace_artifacts(session_id, self.artifact_store.list_all())
            next_state = NodeRuntimeState(
                node_id=prior_state.node_id,
                status="success",
                attempt_count=prior_state.attempt_count,
                last_error=None,
                started_at=prior_state.started_at,
                finished_at=utc_timestamp(),
            )
            self.session_store.update_node_state(session_id, next_state)
            return

        retry_decision = self.retry_policy.decide(prior_state, result)
        if retry_decision.should_retry:
            # 重试时把它放回 pending，而不是直接立刻再次执行。
            # 这样它会在下一轮调度中重新被统一评估，逻辑更干净。
            next_state = NodeRuntimeState(
                node_id=prior_state.node_id,
                status="pending",
                attempt_count=prior_state.attempt_count,
                last_error=result.failure_reason or retry_decision.reason,
                started_at=prior_state.started_at,
                finished_at=utc_timestamp(),
            )
            self.session_store.update_node_state(session_id, next_state)
            return

        # 不能重试的失败会变成终态 failed。
        # 任何依赖它的节点，也就再也不可能变成 ready。
        failed_state = NodeRuntimeState(
            node_id=prior_state.node_id,
            status="failed",
            attempt_count=prior_state.attempt_count,
            last_error=result.failure_reason,
            started_at=prior_state.started_at,
            finished_at=utc_timestamp(),
        )
        self.session_store.update_node_state(session_id, failed_state)
