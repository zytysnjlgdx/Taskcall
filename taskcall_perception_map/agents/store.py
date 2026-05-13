"""内存级 worker agent 生命周期记录存储。"""

from __future__ import annotations

from copy import deepcopy

from taskcall_perception_map.agents.models import WorkerAgentSession


class InMemoryWorkerAgentStore:
    """
    内存级 worker agent 会话存储，追踪每个 agent 的生命周期。

    内部结构：以 agent_id 为 key 存储 WorkerAgentSession。
    所有读取返回 deepcopy，防止外部意外修改内部状态。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, WorkerAgentSession] = {}

    def put(self, session: WorkerAgentSession) -> None:
        """
        存入一个 agent 会话。

        输入:
            session: WorkerAgentSession 对象
        """
        self._sessions[session.identity.agent_id] = deepcopy(session)

    def get(self, agent_id: str) -> WorkerAgentSession:
        """
        按 agent_id 获取一个 agent 会话。

        输入:
            agent_id: agent 唯一标识

        输出:
            WorkerAgentSession 的防御性副本
        """
        return deepcopy(self._sessions[agent_id])

    def update(self, session: WorkerAgentSession) -> None:
        """
        更新一个 agent 会话（覆盖写入）。

        输入:
            session: 更新后的 WorkerAgentSession 对象
        """
        self._sessions[session.identity.agent_id] = deepcopy(session)

    def list_all(self) -> list[WorkerAgentSession]:
        """返回所有 agent 会话的防御性副本列表。"""
        return [deepcopy(session) for session in self._sessions.values()]

    def list_by_session(self, session_id: str) -> list[WorkerAgentSession]:
        """
        返回某次运行（session）中所有 agent 的会话记录。

        输入:
            session_id: 运行会话 id

        输出:
            该会话下所有 WorkerAgentSession 列表
        """
        return [
            deepcopy(session)
            for session in self._sessions.values()
            if session.identity.session_id == session_id
        ]

    def list_by_node(self, node_id: str) -> list[WorkerAgentSession]:
        """
        返回某个节点所有执行尝试的 agent 会话记录。

        输入:
            node_id: 节点 id

        输出:
            该节点所有 WorkerAgentSession 列表（含重试）
        """
        return [
            deepcopy(session)
            for session in self._sessions.values()
            if session.identity.node_id == node_id
        ]
