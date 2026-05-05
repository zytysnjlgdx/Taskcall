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
