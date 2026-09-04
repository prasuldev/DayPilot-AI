"""Domain models shared by storage, scheduling, and interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class Recurrence(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass(frozen=True)
class Goal:
    id: int
    title: str
    created_at: datetime


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    priority: Priority
    estimated_minutes: int
    deadline: datetime | None
    status: TaskStatus
    goal_id: int | None
    created_at: datetime
    recurrence: Recurrence = Recurrence.NONE
    remaining_minutes: int | None = None

    @property
    def minutes_to_schedule(self) -> int:
        return self.remaining_minutes if self.remaining_minutes is not None else self.estimated_minutes


@dataclass(frozen=True)
class ScheduleItem:
    id: int
    schedule_id: int
    task_id: int
    title: str
    start_at: datetime
    end_at: datetime
    status: TaskStatus


@dataclass(frozen=True)
class DailySchedule:
    id: int
    plan_date: date
    work_start: datetime
    work_end: datetime
    created_at: datetime
    items: tuple[ScheduleItem, ...] = ()
