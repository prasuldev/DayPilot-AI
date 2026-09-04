"""Deterministic task ordering and time-slot allocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Priority, Task


@dataclass(frozen=True)
class PlannedSlot:
    task: Task
    start_at: datetime
    end_at: datetime


PRIORITY_RANK = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}


def task_sort_key(task: Task) -> tuple[int, datetime, int]:
    deadline = task.deadline or datetime.max
    return PRIORITY_RANK[task.priority], deadline, task.id


def build_plan(tasks: list[Task], work_start: datetime, work_end: datetime) -> list[PlannedSlot]:
    """Fit complete tasks sequentially into a working window.

    Tasks that do not fit are left unscheduled. A later, shorter task may still fit
    in the remaining time.
    """
    if work_end <= work_start:
        raise ValueError("Work end must be after work start")

    return build_plan_windows(tasks, [(work_start, work_end)])


def validate_windows(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not windows:
        raise ValueError("At least one working window is required")
    ordered = sorted(windows)
    for index, (start, end) in enumerate(ordered):
        if end <= start:
            raise ValueError("Every working window must end after it starts")
        if index and start < ordered[index - 1][1]:
            raise ValueError("Working windows cannot overlap")
    return ordered


def build_plan_windows(tasks: list[Task], windows: list[tuple[datetime, datetime]],
                       break_minutes: int = 0) -> list[PlannedSlot]:
    """Fit complete tasks across ordered availability windows."""
    if break_minutes < 0:
        raise ValueError("Break duration cannot be negative")
    ordered_windows = validate_windows(windows)
    slots: list[PlannedSlot] = []
    window_index = 0
    cursor = ordered_windows[0][0]
    for task in sorted(tasks, key=task_sort_key):
        placed = False
        for candidate_index in range(window_index, len(ordered_windows)):
            window_start, window_end = ordered_windows[candidate_index]
            candidate_start = max(cursor, window_start)
            end_at = candidate_start + timedelta(minutes=task.minutes_to_schedule)
            if end_at <= window_end:
                slots.append(PlannedSlot(task, candidate_start, end_at))
                cursor = end_at + timedelta(minutes=break_minutes)
                window_index = candidate_index
                placed = True
                break
            if candidate_index + 1 < len(ordered_windows):
                cursor = ordered_windows[candidate_index + 1][0]
        if not placed:
            continue
    return slots
