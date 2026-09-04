"""Command-line interface for the productivity agent."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time
from pathlib import Path

from .models import Priority, Recurrence, TaskStatus
from .notifications import process_notifications, watch_notifications
from .scheduler import build_plan_windows
from .storage import Repository


def default_database_path() -> Path:
    configured = os.environ.get("PRODUCTIVITY_AGENT_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library" / "Application Support" / "ProductivityAgent" / "agent.db"


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD") from error


def parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DDTHH:MM") from error


def parse_clock(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use HH:MM") from error


def parse_window(value: str) -> tuple[time, time]:
    try:
        start, end = value.split("-", 1)
        return time.fromisoformat(start), time.fromisoformat(end)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use HH:MM-HH:MM") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="productivity-agent", description="Plan a focused workday")
    parser.add_argument("--db", type=Path, default=default_database_path(), help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)

    add_goal = commands.add_parser("add-goal", help="Create a long-term goal")
    add_goal.add_argument("title")

    add_task = commands.add_parser("add-task", help="Create a task")
    add_task.add_argument("title")
    add_task.add_argument("--priority", choices=[item.value for item in Priority], default="medium")
    add_task.add_argument("--minutes", type=int, required=True)
    add_task.add_argument("--deadline", type=parse_datetime)
    add_task.add_argument("--goal-id", type=int)
    add_task.add_argument("--repeat", choices=[item.value for item in Recurrence], default="none")

    edit_task = commands.add_parser("edit-task", help="Edit a task")
    edit_task.add_argument("task_id", type=int)
    edit_task.add_argument("--title")
    edit_task.add_argument("--priority", choices=[item.value for item in Priority])
    edit_task.add_argument("--minutes", type=int)
    edit_task.add_argument("--deadline", type=parse_datetime)
    edit_task.add_argument("--goal-id", type=int)
    edit_task.add_argument("--repeat", choices=[item.value for item in Recurrence])

    delete_task = commands.add_parser("delete-task", help="Delete a task")
    delete_task.add_argument("task_id", type=int)

    reopen = commands.add_parser("reopen", help="Reopen a task for replanning")
    reopen.add_argument("task_id", type=int)
    reopen.add_argument("--remaining", type=int)

    commands.add_parser("list-tasks", help="List all tasks")

    generate = commands.add_parser("generate", help="Generate and save a daily schedule")
    generate.add_argument("--date", type=parse_date, default=date.today())
    generate.add_argument("--start", type=parse_clock, default=time(9, 0))
    generate.add_argument("--end", type=parse_clock, default=time(17, 0))
    generate.add_argument("--window", type=parse_window, action="append", help="Repeatable HH:MM-HH:MM window")
    generate.add_argument("--break-minutes", type=int, default=0)

    replan = commands.add_parser("replan", help="Move unfinished past sessions into the rest of today")
    replan.add_argument("--end", type=parse_clock, default=time(17, 0))
    replan.add_argument("--break-minutes", type=int, default=0)

    plan = commands.add_parser("plan", help="View a saved daily plan")
    plan.add_argument("--date", type=parse_date, default=date.today())

    for name, help_text in (("complete", "Mark a task complete"), ("skip", "Mark a task skipped")):
        status_command = commands.add_parser(name, help=help_text)
        status_command.add_argument("task_id", type=int)

    notifications = commands.add_parser("notifications", help="Send due macOS schedule alerts")
    notifications.add_argument("--upcoming-minutes", type=int, default=10)
    notifications.add_argument("--interval", type=int, default=30)
    notifications.add_argument("--once", action="store_true", help="Check once instead of watching")
    commands.add_parser("install-service", help="Run notifications automatically after macOS login")
    commands.add_parser("uninstall-service", help="Remove the background notification service")
    api = commands.add_parser("api", help="Run the optional FastAPI service")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    return parser


def print_schedule(repository: Repository, plan_date: date) -> None:
    schedule = repository.get_schedule(plan_date)
    if not schedule:
        print(f"No plan saved for {plan_date.isoformat()}.")
        return
    print(f"Plan for {plan_date.isoformat()} ({schedule.work_start:%H:%M}-{schedule.work_end:%H:%M})")
    if not schedule.items:
        print("  No tasks fit this working window.")
    for item in schedule.items:
        print(f"  {item.start_at:%H:%M}-{item.end_at:%H:%M}  #{item.task_id} {item.title} [{item.status.value}]")


def run(arguments: argparse.Namespace) -> int:
    repository = Repository(arguments.db)
    repository.initialize()
    if arguments.command == "add-goal":
        goal = repository.add_goal(arguments.title)
        print(f"Added goal #{goal.id}: {goal.title}")
    elif arguments.command == "add-task":
        task = repository.add_task(
            arguments.title, Priority(arguments.priority), arguments.minutes,
            arguments.deadline, arguments.goal_id,
            Recurrence(arguments.repeat),
        )
        print(f"Added task #{task.id}: {task.title}")
    elif arguments.command == "edit-task":
        current = repository.get_task(arguments.task_id)
        if not current:
            raise ValueError(f"Task {arguments.task_id} does not exist")
        task = repository.update_task(
            current.id, title=arguments.title or current.title,
            priority=Priority(arguments.priority) if arguments.priority else current.priority,
            estimated_minutes=arguments.minutes or current.estimated_minutes,
            deadline=arguments.deadline if arguments.deadline is not None else current.deadline,
            goal_id=arguments.goal_id if arguments.goal_id is not None else current.goal_id,
            recurrence=Recurrence(arguments.repeat) if arguments.repeat else current.recurrence,
        )
        print(f"Updated task #{task.id}: {task.title}")
    elif arguments.command == "delete-task":
        repository.delete_task(arguments.task_id)
        print(f"Deleted task #{arguments.task_id}.")
    elif arguments.command == "reopen":
        repository.reopen_task(arguments.task_id, arguments.remaining)
        print(f"Task #{arguments.task_id} reopened.")
    elif arguments.command == "list-tasks":
        tasks = repository.list_tasks()
        if not tasks:
            print("No tasks yet.")
        for task in tasks:
            deadline = task.deadline.strftime("%Y-%m-%d %H:%M") if task.deadline else "none"
            repeat = f" | repeats {task.recurrence.value}" if task.recurrence is not Recurrence.NONE else ""
            print(f"#{task.id} {task.title} | {task.priority.value} | {task.minutes_to_schedule}m | deadline {deadline} | {task.status.value}{repeat}")
    elif arguments.command == "generate":
        windows = [(datetime.combine(arguments.date, start), datetime.combine(arguments.date, end))
                   for start, end in arguments.window] if arguments.window else [
                       (datetime.combine(arguments.date, arguments.start), datetime.combine(arguments.date, arguments.end))]
        tasks = repository.tasks_for_planning(arguments.date)
        slots = build_plan_windows(tasks, windows, arguments.break_minutes)
        repository.save_availability(arguments.date, windows)
        repository.replace_schedule(arguments.date, windows[0][0], windows[-1][1], slots)
        print_schedule(repository, arguments.date)
        unscheduled = len(tasks) - len(slots)
        if unscheduled:
            print(f"{unscheduled} task(s) did not fit and remain pending.")
    elif arguments.command == "replan":
        now = datetime.now().replace(second=0, microsecond=0)
        carried = repository.carry_over_unfinished(now)
        end = datetime.combine(now.date(), arguments.end)
        slots = build_plan_windows(repository.tasks_for_planning(now.date()), [(now, end)], arguments.break_minutes)
        repository.save_availability(now.date(), [(now, end)])
        repository.replace_schedule(now.date(), now, end, slots)
        print(f"Carried over {carried} unfinished task(s).")
        print_schedule(repository, now.date())
    elif arguments.command == "plan":
        print_schedule(repository, arguments.date)
    elif arguments.command in ("complete", "skip"):
        status = TaskStatus.COMPLETED if arguments.command == "complete" else TaskStatus.SKIPPED
        repository.set_task_status(arguments.task_id, status)
        print(f"Task #{arguments.task_id} marked {status.value}.")
    elif arguments.command == "notifications":
        if arguments.upcoming_minutes < 0 or arguments.interval <= 0:
            raise ValueError("Notification timings must be positive")
        if arguments.once:
            count = process_notifications(repository, upcoming_minutes=arguments.upcoming_minutes)
            print(f"Sent {count} notification(s).")
        else:
            print("Watching the schedule for notifications. Press Ctrl-C to stop.")
            watch_notifications(repository, arguments.upcoming_minutes, arguments.interval)
    elif arguments.command == "install-service":
        from .service import install_notification_service
        launcher = Path(__file__).resolve().parents[2] / "productivity-agent"
        target = install_notification_service(launcher, Path(arguments.db).expanduser())
        print(f"Installed background notifications: {target}")
    elif arguments.command == "uninstall-service":
        from .service import uninstall_notification_service
        uninstall_notification_service()
        print("Removed background notifications.")
    elif arguments.command == "api":
        try:
            import uvicorn
        except ImportError as error:
            raise RuntimeError("Install API support with: pip install fastapi uvicorn") from error
        from .api import create_app
        uvicorn.run(create_app(arguments.db), host=arguments.host, port=arguments.port)
    return 0


def main() -> None:
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except (ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
