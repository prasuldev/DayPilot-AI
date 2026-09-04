"""SQLite persistence and repository operations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from .models import DailySchedule, Goal, Priority, Recurrence, ScheduleItem, Task, TaskStatus
from .scheduler import PlannedSlot


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    estimated_minutes INTEGER NOT NULL CHECK (estimated_minutes > 0),
    deadline TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'scheduled', 'completed', 'skipped')),
    goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL UNIQUE,
    work_start TEXT NOT NULL,
    work_end TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('scheduled', 'completed', 'skipped')),
    start_notified INTEGER NOT NULL DEFAULT 0,
    end_notified INTEGER NOT NULL DEFAULT 0,
    upcoming_notified INTEGER NOT NULL DEFAULT 0,
    UNIQUE(schedule_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_schedule_items_time ON schedule_items(start_at, end_at);

CREATE TABLE IF NOT EXISTS availability_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL
);
"""


class Repository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
            if "recurrence" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none'")
            if "remaining_minutes" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN remaining_minutes INTEGER")

    def add_goal(self, title: str) -> Goal:
        title = title.strip()
        if not title:
            raise ValueError("Goal title cannot be empty")
        created_at = datetime.now().replace(microsecond=0)
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO goals(title, created_at) VALUES (?, ?)",
                (title, created_at.isoformat()),
            )
            goal_id = int(cursor.lastrowid)
        return Goal(goal_id, title, created_at)

    def list_goals(self) -> list[Goal]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM goals ORDER BY id").fetchall()
        return [Goal(row["id"], row["title"], datetime.fromisoformat(row["created_at"])) for row in rows]

    def add_task(
        self,
        title: str,
        priority: Priority,
        estimated_minutes: int,
        deadline: datetime | None = None,
        goal_id: int | None = None,
        recurrence: Recurrence = Recurrence.NONE,
    ) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        if estimated_minutes <= 0:
            raise ValueError("Estimated duration must be greater than zero")
        created_at = datetime.now().replace(microsecond=0)
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO tasks
                   (title, priority, estimated_minutes, deadline, status, goal_id, created_at,
                    recurrence, remaining_minutes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    title,
                    priority.value,
                    estimated_minutes,
                    deadline.isoformat() if deadline else None,
                    TaskStatus.PENDING.value,
                    goal_id,
                    created_at.isoformat(),
                    recurrence.value,
                    estimated_minutes,
                ),
            )
            task_id = int(cursor.lastrowid)
        return Task(task_id, title, priority, estimated_minutes, deadline, TaskStatus.PENDING,
                    goal_id, created_at, recurrence, estimated_minutes)

    def update_task(self, task_id: int, *, title: str, priority: Priority,
                    estimated_minutes: int, deadline: datetime | None,
                    goal_id: int | None, recurrence: Recurrence) -> Task:
        if not title.strip() or estimated_minutes <= 0:
            raise ValueError("Title and positive duration are required")
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE tasks SET title=?, priority=?, estimated_minutes=?, deadline=?,
                   goal_id=?, recurrence=?, remaining_minutes=? WHERE id=?""",
                (title.strip(), priority.value, estimated_minutes,
                 deadline.isoformat() if deadline else None, goal_id, recurrence.value,
                 estimated_minutes, task_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} does not exist")
        task = self.get_task(task_id)
        assert task is not None
        return task

    def delete_task(self, task_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} does not exist")

    def get_task(self, task_id: int) -> Task | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def list_tasks(self, statuses: tuple[TaskStatus, ...] | None = None) -> list[Task]:
        query = "SELECT * FROM tasks"
        parameters: tuple[str, ...] = ()
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            parameters = tuple(status.value for status in statuses)
        query += " ORDER BY id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._task_from_row(row) for row in rows]

    def set_task_status(self, task_id: int, status: TaskStatus) -> None:
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not existing:
                raise ValueError(f"Task {task_id} does not exist")
            cursor = connection.execute("UPDATE tasks SET status = ? WHERE id = ?", (status.value, task_id))
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} does not exist")
            if status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
                connection.execute(
                    "UPDATE schedule_items SET status = ? WHERE task_id = ? AND status = 'scheduled'",
                    (status.value, task_id),
                )
            if status is TaskStatus.COMPLETED and Recurrence(existing["recurrence"]) is not Recurrence.NONE:
                delta_days = 1 if existing["recurrence"] == "daily" else 7
                from datetime import timedelta
                deadline = datetime.fromisoformat(existing["deadline"]) + timedelta(days=delta_days) if existing["deadline"] else None
                connection.execute(
                    """INSERT INTO tasks(title, priority, estimated_minutes, deadline, status,
                       goal_id, created_at, recurrence, remaining_minutes)
                       VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                    (existing["title"], existing["priority"], existing["estimated_minutes"],
                     deadline.isoformat() if deadline else None, existing["goal_id"],
                     datetime.now().replace(microsecond=0).isoformat(), existing["recurrence"],
                     existing["estimated_minutes"]),
                )

    def reopen_task(self, task_id: int, remaining_minutes: int | None = None) -> None:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} does not exist")
        remaining = remaining_minutes if remaining_minutes is not None else task.estimated_minutes
        if remaining <= 0:
            raise ValueError("Remaining duration must be positive")
        with self.connect() as connection:
            connection.execute("UPDATE tasks SET status='pending', remaining_minutes=? WHERE id=?", (remaining, task_id))

    def carry_over_unfinished(self, now: datetime) -> int:
        """Return ended, unfinished sessions to pending for replanning."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT si.task_id FROM schedule_items si
                   JOIN tasks t ON t.id=si.task_id
                   WHERE si.end_at <= ? AND si.status='scheduled' AND t.status='scheduled'""",
                (now.isoformat(),),
            ).fetchall()
            task_ids = [row["task_id"] for row in rows]
            for task_id in task_ids:
                connection.execute("UPDATE tasks SET status='pending' WHERE id=?", (task_id,))
                connection.execute("UPDATE schedule_items SET status='skipped' WHERE task_id=? AND status='scheduled'", (task_id,))
        return len(task_ids)

    def save_availability(self, plan_date: date, windows: list[tuple[datetime, datetime]]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM availability_windows WHERE plan_date=?", (plan_date.isoformat(),))
            connection.executemany(
                "INSERT INTO availability_windows(plan_date,start_at,end_at) VALUES(?,?,?)",
                [(plan_date.isoformat(), start.isoformat(), end.isoformat()) for start, end in windows],
            )

    def get_availability(self, plan_date: date) -> list[tuple[datetime, datetime]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT start_at,end_at FROM availability_windows WHERE plan_date=? ORDER BY start_at",
                (plan_date.isoformat(),),
            ).fetchall()
        return [(datetime.fromisoformat(row["start_at"]), datetime.fromisoformat(row["end_at"])) for row in rows]

    def replace_schedule(
        self,
        plan_date: date,
        work_start: datetime,
        work_end: datetime,
        slots: list[PlannedSlot],
    ) -> DailySchedule:
        created_at = datetime.now().replace(microsecond=0)
        with self.connect() as connection:
            old_schedule = connection.execute(
                "SELECT id FROM schedules WHERE plan_date = ?", (plan_date.isoformat(),)
            ).fetchone()
            if old_schedule:
                connection.execute(
                    """UPDATE tasks SET status = 'pending'
                       WHERE status = 'scheduled' AND id IN
                       (SELECT task_id FROM schedule_items WHERE schedule_id = ?)""",
                    (old_schedule["id"],),
                )
                connection.execute("DELETE FROM schedules WHERE id = ?", (old_schedule["id"],))

            cursor = connection.execute(
                """INSERT INTO schedules(plan_date, work_start, work_end, created_at)
                   VALUES (?, ?, ?, ?)""",
                (plan_date.isoformat(), work_start.isoformat(), work_end.isoformat(), created_at.isoformat()),
            )
            schedule_id = int(cursor.lastrowid)
            for slot in slots:
                connection.execute(
                    """INSERT INTO schedule_items
                       (schedule_id, task_id, start_at, end_at, status)
                       VALUES (?, ?, ?, ?, 'scheduled')""",
                    (schedule_id, slot.task.id, slot.start_at.isoformat(), slot.end_at.isoformat()),
                )
                connection.execute(
                    "UPDATE tasks SET status = 'scheduled' WHERE id = ? AND status = 'pending'",
                    (slot.task.id,),
                )
        schedule = self.get_schedule(plan_date)
        if schedule is None:  # Defensive: the transaction above should always create it.
            raise RuntimeError("Schedule could not be saved")
        return schedule

    def tasks_for_planning(self, plan_date: date) -> list[Task]:
        """Return pending tasks plus non-terminal tasks already planned for this day."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT t.* FROM tasks t
                   LEFT JOIN schedule_items si ON si.task_id = t.id
                   LEFT JOIN schedules s ON s.id = si.schedule_id
                   WHERE t.status = 'pending'
                      OR (t.status = 'scheduled' AND s.plan_date = ?)
                   ORDER BY t.id""",
                (plan_date.isoformat(),),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            priority=Priority(row["priority"]),
            estimated_minutes=row["estimated_minutes"],
            deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None,
            status=TaskStatus(row["status"]),
            goal_id=row["goal_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            recurrence=Recurrence(row["recurrence"]),
            remaining_minutes=row["remaining_minutes"],
        )

    def get_schedule(self, plan_date: date) -> DailySchedule | None:
        with self.connect() as connection:
            schedule_row = connection.execute(
                "SELECT * FROM schedules WHERE plan_date = ?", (plan_date.isoformat(),)
            ).fetchone()
            if not schedule_row:
                return None
            item_rows = connection.execute(
                """SELECT si.*, t.title FROM schedule_items si
                   JOIN tasks t ON t.id = si.task_id
                   WHERE si.schedule_id = ? ORDER BY si.start_at""",
                (schedule_row["id"],),
            ).fetchall()
        items = tuple(
            ScheduleItem(
                row["id"], row["schedule_id"], row["task_id"], row["title"],
                datetime.fromisoformat(row["start_at"]), datetime.fromisoformat(row["end_at"]),
                TaskStatus(row["status"]),
            )
            for row in item_rows
        )
        return DailySchedule(
            schedule_row["id"], date.fromisoformat(schedule_row["plan_date"]),
            datetime.fromisoformat(schedule_row["work_start"]),
            datetime.fromisoformat(schedule_row["work_end"]),
            datetime.fromisoformat(schedule_row["created_at"]), items,
        )

    def claim_notification_events(self, now: datetime, upcoming_minutes: int = 10) -> list[tuple[str, str]]:
        """Atomically claim alert events that should fire at *now*."""
        from datetime import timedelta

        events: list[tuple[str, str]] = []
        upcoming_cutoff = now + timedelta(minutes=upcoming_minutes)
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT si.id, si.start_at, si.end_at, si.start_notified,
                          si.end_notified, si.upcoming_notified, t.title
                   FROM schedule_items si JOIN tasks t ON t.id = si.task_id
                   WHERE si.status = 'scheduled' AND si.end_at >= ?
                   ORDER BY si.start_at""",
                (now.isoformat(),),
            ).fetchall()
            for row in rows:
                start_at = datetime.fromisoformat(row["start_at"])
                end_at = datetime.fromisoformat(row["end_at"])
                if start_at > now and start_at <= upcoming_cutoff and not row["upcoming_notified"]:
                    events.append(("Upcoming task", f"{row['title']} starts at {start_at:%H:%M}"))
                    connection.execute(
                        "UPDATE schedule_items SET upcoming_notified = 1 WHERE id = ?", (row["id"],)
                    )
                if start_at <= now < end_at and not row["start_notified"]:
                    events.append(("Task starting", row["title"]))
                    connection.execute("UPDATE schedule_items SET start_notified = 1 WHERE id = ?", (row["id"],))

            ended = connection.execute(
                """SELECT si.id, t.title FROM schedule_items si
                   JOIN tasks t ON t.id = si.task_id
                   WHERE si.status = 'scheduled' AND si.end_at <= ? AND si.end_notified = 0
                   ORDER BY si.end_at""",
                (now.isoformat(),),
            ).fetchall()
            for row in ended:
                events.append(("Task session ended", row["title"]))
                connection.execute("UPDATE schedule_items SET end_notified = 1 WHERE id = ?", (row["id"],))
        return events
