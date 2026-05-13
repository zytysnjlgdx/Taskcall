"""Request/result models shared by planner implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from taskcall_perception_map.domain.models import PlanGraph

if TYPE_CHECKING:
    from taskcall_perception_map.planner.contracts import RetrievedCase


@dataclass(slots=True)
class PlannerRequest:
    """Normalized planner input for turning a question into a DAG."""

    question_text: str
    retrieved_cases: list["RetrievedCase"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlannerDebugInfo:
    """Optional debug payload retained by planner implementations."""

    prompt_text: str | None = None
    raw_response: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlannerResult:
    """Planner output plus optional debug information."""

    plan: PlanGraph
    debug: PlannerDebugInfo | None = None
