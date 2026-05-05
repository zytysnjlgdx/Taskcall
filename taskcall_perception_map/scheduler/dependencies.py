"""依赖关系辅助函数。

这个文件只做一件事：根据节点依赖和当前状态，判断谁现在可以跑。
它不负责执行节点，只负责回答调度层的两个问题：

1. 哪些节点现在是 ready？
2. 哪些 pending 节点应该被提升成 ready？
"""

from __future__ import annotations

from taskcall_perception_map.domain.models import NodeRuntimeState, PlanGraph


def get_ready_node_ids(
    plan: PlanGraph,
    node_states: dict[str, NodeRuntimeState],
) -> list[str]:
    """返回当前依赖已经全部满足的节点 id 列表。

    判定条件非常简单：
    - 节点当前状态必须还是 pending 或 ready
    - 它 depends_on 里的所有节点都已经 success
    """
    ready_node_ids: list[str] = []
    for node in plan.nodes:
        state = node_states[node.id]
        if state.status not in {"pending", "ready"}:
            continue
        if all(node_states[dependency].status == "success" for dependency in node.depends_on):
            ready_node_ids.append(node.id)
    return ready_node_ids


def sync_ready_states(
    plan: PlanGraph,
    node_states: dict[str, NodeRuntimeState],
) -> None:
    """把已经被解锁的 pending 节点升级成 ready。

    这个函数会直接原地修改 ``node_states``。
    """
    ready_node_ids = set(get_ready_node_ids(plan, node_states))
    for node in plan.nodes:
        state = node_states[node.id]
        if state.status == "pending" and node.id in ready_node_ids:
            state.status = "ready"


def has_unfinished_nodes(node_states: dict[str, NodeRuntimeState]) -> bool:
    """只要还有节点没进入终态，就返回 True。"""
    return any(state.status in {"pending", "ready", "running"} for state in node_states.values())
