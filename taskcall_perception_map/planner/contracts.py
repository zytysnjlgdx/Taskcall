"""Planner-side contracts kept separate from runtime mechanics.

The current project only defines interfaces here, which lets future
planners or case-retrieval systems plug in without changing the
scheduler/runtime layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from taskcall_perception_map.domain.models import PlanGraph

if TYPE_CHECKING:
    from taskcall_perception_map.planner.models import PlannerRequest, PlannerResult


@dataclass(slots=True)
class RetrievedCase:
    """One retrieved planning example that may guide a new plan."""

    case_id: str
    question_text: str
    plan: PlanGraph
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class CaseRetriever(Protocol):
    """Lookup similar historical cases for a new user question."""

    async def retrieve(self, question_text: str, top_k: int) -> list[RetrievedCase]:
        ...


class OnlinePlanner(Protocol):
    """Build a fresh plan graph from the current question and past cases."""

    async def plan(
        self,
        question_text: str,
        retrieved_cases: list[RetrievedCase],
    ) -> PlanGraph:
        ...


class PlanningAgent(Protocol):
    """Higher-level planner interface with normalized request/result objects."""

    async def plan(self, request: "PlannerRequest") -> "PlannerResult":
        ...


class OfflineCaseBuilder(Protocol):
    """Convert training data into reusable retrieved cases."""

    async def build(self, training_example: Any) -> RetrievedCase:
        ...
