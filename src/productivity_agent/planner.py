"""Extension point for future LLM-assisted task decomposition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import Priority


@dataclass(frozen=True)
class TaskSuggestion:
    title: str
    priority: Priority
    estimated_minutes: int


class PlanningProvider(Protocol):
    def suggest_tasks(self, goal: str) -> list[TaskSuggestion]: ...


class DeterministicPlanningProvider:
    """Useful offline fallback; replace through dependency injection, not scheduler changes."""

    def suggest_tasks(self, goal: str) -> list[TaskSuggestion]:
        goal = goal.strip()
        if not goal:
            raise ValueError("Goal cannot be empty")
        return [
            TaskSuggestion(f"Define success criteria for {goal}", Priority.HIGH, 30),
            TaskSuggestion(f"Complete the first focused session for {goal}", Priority.HIGH, 60),
            TaskSuggestion(f"Review progress on {goal}", Priority.MEDIUM, 20),
        ]
