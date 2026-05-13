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
    """
    内存级会话快照存储，管理每次运行的全局状态。

    作用：存储和更新 SessionSnapshot（包含 PlanGraph、节点状态、产物列表）。
         所有读取都返回 deepcopy，防止外部意外修改内部状态。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionSnapshot] = {}

    def create(self, plan: PlanGraph, session_id: str | None = None) -> SessionSnapshot:
        """
        创建一个新的运行会话，所有节点初始为 pending。

        输入:
            plan: PlanGraph 对象
            session_id: 可选的会话 id，不传则自动生成 uuid

        输出:
            SessionSnapshot: 新建的会话快照（防御性副本）
        """
        resolved_session_id = session_id or str(uuid4())
        snapshot = SessionSnapshot(
            session_id=resolved_session_id,
            plan=plan,
            node_states=create_initial_node_states(plan),
        )
        self._sessions[resolved_session_id] = snapshot
        return deepcopy(snapshot)

    def get(self, session_id: str) -> SessionSnapshot:
        """
        读取某个会话的最新快照。

        输入:
            session_id: 会话 id

        输出:
            SessionSnapshot: 快照的防御性副本
        """
        snapshot = self._sessions[session_id]
        return deepcopy(snapshot)

    def update_node_state(self, session_id: str, state: NodeRuntimeState) -> None:
        """
        更新某个节点的运行状态，同时刷新快照时间戳。

        输入:
            session_id: 会话 id
            state: 新的节点状态（NodeRuntimeState）
        """
        snapshot = self._sessions[session_id]
        snapshot.node_states[state.node_id] = deepcopy(state)
        snapshot.updated_at = utc_timestamp()

    def replace_artifacts(
        self,
        session_id: str,
        artifacts: list[SemanticArtifact],
    ) -> None:
        """
        替换会话快照中的产物列表，同时刷新时间戳。

        输入:
            session_id: 会话 id
            artifacts: 最新的产物列表
        """
        snapshot = self._sessions[session_id]
        snapshot.artifacts = deepcopy(artifacts)
        snapshot.updated_at = utc_timestamp()

    def list_sessions(self) -> list[SessionSnapshot]:
        """返回所有会话快照的防御性副本列表。"""
        return [deepcopy(snapshot) for snapshot in self._sessions.values()]
