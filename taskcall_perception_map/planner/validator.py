"""Validation protocol for plan graphs produced by a planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from taskcall_perception_map.domain.models import PlanGraph


@dataclass(slots=True)
class PlanValidationIssue:
    """One concrete issue found in a candidate plan graph."""

    message: str
    node_id: str | None = None


@dataclass(slots=True)
class PlanValidationResult:
    """Boolean result plus the list of issues discovered."""

    ok: bool
    issues: list[PlanValidationIssue] = field(default_factory=list)


class PlanValidator(Protocol):
    """Check whether a planner-produced graph is acceptable for execution."""

    def validate(self, plan: PlanGraph) -> PlanValidationResult:
        ...


class NoOpPlanValidator:
    """Default placeholder validator used while real rules are pending."""

    def validate(self, plan: PlanGraph) -> PlanValidationResult:
        return PlanValidationResult(ok=True)


class StructuralPlanValidator:
    """Minimal structural validator for scheduler-safe plan graphs."""

    def validate(self, plan: PlanGraph) -> PlanValidationResult:
        issues: list[PlanValidationIssue] = []
        node_ids = [node.id for node in plan.nodes]
        seen_ids: set[str] = set()

        if not plan.nodes:
            issues.append(PlanValidationIssue(message="Plan graph must contain at least one node."))

        for node in plan.nodes:
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

            if not node.goal.strip():
                issues.append(
                    PlanValidationIssue(
                        message="Node goal must not be empty.",
                        node_id=node.id,
                    )
                )

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
                if not selector.field.strip():
                    issues.append(
                        PlanValidationIssue(
                            message="Input selector field must not be empty.",
                            node_id=node.id,
                        )
                    )

        issues.extend(_detect_cycles(plan))
        return PlanValidationResult(ok=not issues, issues=issues)


def _detect_cycles(plan: PlanGraph) -> list[PlanValidationIssue]:
    node_map = {node.id: node for node in plan.nodes}
    visiting: set[str] = set()
    visited: set[str] = set()
    issues: list[PlanValidationIssue] = []

    def visit(node_id: str, trail: list[str]) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
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
