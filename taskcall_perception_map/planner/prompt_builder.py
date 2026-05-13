"""Prompt-builder protocol for LLM-based planner implementations."""

from __future__ import annotations

from typing import Protocol

from taskcall_perception_map.planner.models import PlannerRequest


class PlannerPromptBuilder(Protocol):
    """Build a planner prompt from the normalized request object."""

    def build(self, request: PlannerRequest) -> str:
        ...
