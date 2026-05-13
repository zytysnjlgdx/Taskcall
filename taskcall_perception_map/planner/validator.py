"""校验 planner 产出的 PlanGraph 是否可以安全交给 scheduler 执行。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from taskcall_perception_map.domain.models import PlanGraph


@dataclass(slots=True)
class PlanValidationIssue:
    """校验发现的单个问题。

    字段:
        message: 错误描述
        node_id: 问题所在的节点 id（可选，全局问题时为 None）
    """

    message: str
    node_id: str | None = None


@dataclass(slots=True)
class PlanValidationResult:
    """校验结果。

    字段:
        ok: 是否全部通过
        issues: 发现的问题列表（ok=True 时为空）
    """

    ok: bool
    issues: list[PlanValidationIssue] = field(default_factory=list)


class PlanValidator(Protocol):
    """校验器接口，所有校验器必须实现 validate 方法。"""

    def validate(self, plan: PlanGraph) -> PlanValidationResult:
        ...


class NoOpPlanValidator:
    """空校验器，直接返回 ok=True，用于开发/测试阶段跳过校验。"""

    def validate(self, plan: PlanGraph) -> PlanValidationResult:
        return PlanValidationResult(ok=True)


class StructuralPlanValidator:
    """结构校验器，检查 PlanGraph 是否满足 scheduler 的基本要求。"""

    def validate(self, plan: PlanGraph) -> PlanValidationResult:
        """
        校验 PlanGraph 的结构合法性。

        输入:
            plan: planner 产出的 PlanGraph 对象

        输出:
            PlanValidationResult: ok=True 表示通过，ok=False 表示有问题

        校验规则:
            1. 节点数 ≥ 1
            2. 节点 id 非空且不重复
            3. goal 非空
            4. 每个节点至少有一个 output，output field 非空且不重复
            5. depends_on 不能引用自己，不能引用不存在的节点
            6. inputs_from_subproblems 不能引用不存在的节点，field 非空，且上游节点确实产出了该 field
            7. 依赖图不能有环
        """
        issues: list[PlanValidationIssue] = []
        node_ids = [node.id for node in plan.nodes]
        node_map = {node.id: node for node in plan.nodes}
        seen_ids: set[str] = set()

        if not plan.nodes:
            issues.append(PlanValidationIssue(message="Plan graph must contain at least one node."))

        for node in plan.nodes:
            # 校验节点 id 非空且不重复
            if not node.id.strip():
                issues.append(PlanValidationIssue(message="Node id must not be empty."))
                continue
            if node.id in seen_ids:
                issues.append(
                    PlanValidationIssue(
                        message=f"Duplicate node id '{node.id}'.",
                        node_id=node.id,
                    )
                )
            seen_ids.add(node.id)

            # 校验 goal 非空
            if not node.goal.strip():
                issues.append(
                    PlanValidationIssue(
                        message="Node goal must not be empty.",
                        node_id=node.id,
                    )
                )

            # 校验 outputs：至少一个，field 非空且不重复
            output_fields: set[str] = set()
            if not node.outputs:
                issues.append(
                    PlanValidationIssue(
                        message="Node must declare at least one output.",
                        node_id=node.id,
                    )
                )
            for output in node.outputs:
                if not output.field.strip():
                    issues.append(
                        PlanValidationIssue(
                            message="Output field must not be empty.",
                            node_id=node.id,
                        )
                    )
                    continue
                if output.field in output_fields:
                    issues.append(
                        PlanValidationIssue(
                            message=f"Duplicate output field '{output.field}'.",
                            node_id=node.id,
                        )
                    )
                output_fields.add(output.field)

            # 校验 depends_on：不能引用自己，不能引用不存在的节点
            for dependency in node.depends_on:
                if dependency == node.id:
                    issues.append(
                        PlanValidationIssue(
                            message="Node cannot depend on itself.",
                            node_id=node.id,
                        )
                    )
                if dependency not in node_ids:
                    issues.append(
                        PlanValidationIssue(
                            message=f"Unknown dependency '{dependency}'.",
                            node_id=node.id,
                        )
                    )

            # 校验 inputs_from_subproblems：不能引用不存在的节点，field 非空，且上游节点确实产出了该 field
            for selector in node.inputs_from_subproblems:
                if selector.source_node_id not in node_ids:
                    issues.append(
                        PlanValidationIssue(
                            message=(
                                "Input selector references unknown node "
                                f"'{selector.source_node_id}'."
                            ),
                            node_id=node.id,
                        )
                    )
                elif not selector.field.strip():
                    issues.append(
                        PlanValidationIssue(
                            message="Input selector field must not be empty.",
                            node_id=node.id,
                        )
                    )
                else:
                    # 节点存在且 field 非空，检查上游节点是否真的产出了该 field
                    source_node = node_map[selector.source_node_id]
                    source_fields = {o.field for o in source_node.outputs}
                    if selector.field not in source_fields:
                        issues.append(
                            PlanValidationIssue(
                                message=(
                                    f"Input selector references field '{selector.field}' "
                                    f"from node '{selector.source_node_id}', "
                                    f"but that node only outputs {source_fields}."
                                ),
                                node_id=node.id,
                            )
                        )

        # 校验依赖图无环
        issues.extend(_detect_cycles(plan))
        return PlanValidationResult(ok=not issues, issues=issues)


def _detect_cycles(plan: PlanGraph) -> list[PlanValidationIssue]:
    """
    检测 PlanGraph 的依赖图中是否存在环。

    输入:
        plan: PlanGraph 对象

    输出:
        list[PlanValidationIssue]: 有环时返回包含环路径的 issue 列表，无环时返回空列表

    算法:
        DFS 拓扑排序，用 visiting/visited 两个集合追踪状态。
        visiting 中的节点再次被访问到，说明存在环。
    """
    node_map = {node.id: node for node in plan.nodes}
    visiting: set[str] = set()  # 当前 DFS 路径上的节点（正在访问）
    visited: set[str] = set()   # 已完成访问的节点
    issues: list[PlanValidationIssue] = []

    def visit(node_id: str, trail: list[str]) -> None:
        """递归访问节点，发现环时记录到 issues 中。"""
        if node_id in visited:
            return  # 已经访问过，跳过
        if node_id in visiting:
            # 在当前路径上再次遇到，说明有环
            cycle = " -> ".join(trail + [node_id])
            issues.append(
                PlanValidationIssue(
                    message=f"Dependency cycle detected: {cycle}.",
                    node_id=node_id,
                )
            )
            return

        visiting.add(node_id)
        node = node_map[node_id]
        for dependency in node.depends_on:
            if dependency in node_map:
                visit(dependency, trail + [node_id])
        visiting.remove(node_id)
        visited.add(node_id)

    for node in plan.nodes:
        visit(node.id, [])
    return issues
