"""Response-parser protocol for planner model outputs."""

from __future__ import annotations

from typing import Protocol

from taskcall_perception_map.domain.models import PlanGraph


class PlannerResponseParser(Protocol):
    """Turn raw planner model output into a validated plan graph."""

    def parse(self, text: str) -> PlanGraph:
        ...
