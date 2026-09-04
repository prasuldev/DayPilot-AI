# Personal AI Productivity Agent

A local-first Python application that stores goals and tasks, builds a deterministic daily plan, tracks completion, and sends macOS desktop notifications. This first version deliberately keeps scheduling rules separate from interfaces so a FastAPI service and LLM planning adapter can be added later.

## Desktop app

The project now includes a private local dashboard that opens in your web browser and stores everything on your Mac. Double-click:

```text
Personal AI Productivity Agent.app
```

Or launch it from the project terminal:

```bash
./productivity-app
```

The dashboard uses the same database as the CLI. It can add tasks, show task state, complete, skip, reopen or delete tasks, create daily plans, and display the resulting timeline. Enter multiple availability windows separated by commas, for example `09:00-12:00,13:00-17:00`. It listens only at `http://127.0.0.1:8765`; nothing is hosted online. Keep the terminal open and press Ctrl-C to stop the app.

## What it does

- Stores goals, tasks, daily schedules, and completion state in SQLite.
- Tracks task title, priority, estimated duration, deadline, goal, and status.
- Schedules complete tasks inside a chosen working window.
- Orders tasks deterministically by priority, then deadline, then creation order.
- Leaves tasks pending when they do not fit; it never truncates a task silently.
- Sends one-time upcoming, start, and end alerts through macOS Notification Center.
- Provides commands to add, plan, view, complete, and skip work.
- Supports task editing/deletion, daily or weekly recurrence, breaks, multiple work windows, and unfinished-work replanning.

## Requirements

- Python 3.10 or newer
- macOS for desktop notifications (all other features are cross-platform)

The project has no runtime dependencies outside the Python standard library.

## Setup

From this project directory, make the included launcher executable once:

```bash
chmod +x productivity-agent
```

It runs with the system Python and requires no package download. In all examples below, use `./productivity-agent`.

Optional: if you prefer an activated virtual environment and a command without `./`, install it in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

The default database is stored at:

```text
~/Library/Application Support/ProductivityAgent/agent.db
```

Every command accepts `--db PATH` before the command name if you want another location. You can also set `PRODUCTIVITY_AGENT_DB`.

## Quick start

Add an optional goal and some tasks:

```bash
./productivity-agent add-goal "Prepare for interviews"
./productivity-agent add-task "Practice Python" --priority high --minutes 60 --deadline 2026-09-05T17:00 --goal-id 1
./productivity-agent add-task "Update portfolio" --priority medium --minutes 45
./productivity-agent add-task "Daily review" --priority medium --minutes 20 --repeat daily
./productivity-agent list-tasks
```

Generate and view today's plan (the defaults are 09:00–17:00):

```bash
./productivity-agent generate --start 09:00 --end 17:00
./productivity-agent plan
```

Multiple work windows and breaks:

```bash
./productivity-agent generate --window 09:00-12:00 --window 13:00-17:00 --break-minutes 10
```

You can plan another day with `--date YYYY-MM-DD` on both commands.

Record outcomes using the task number shown in the plan:

```bash
./productivity-agent complete 1
./productivity-agent skip 2
./productivity-agent reopen 2 --remaining 20
./productivity-agent edit-task 2 --minutes 30 --priority high
./productivity-agent delete-task 2
```

To carry sessions that ended without completion into the rest of today:

```bash
./productivity-agent replan --end 18:00 --break-minutes 10
```

## Desktop notifications

Keep this running during the workday:

```bash
./productivity-agent notifications
```

It checks every 30 seconds and sends an alert 10 minutes before a session, when it starts, and when it ends. Customize those values with:

```bash
./productivity-agent notifications --upcoming-minutes 5 --interval 15
```

For a single check, use `./productivity-agent notifications --once`. On first use, macOS may ask permission for your terminal application to send notifications. Stop the watcher with Ctrl-C.

To start notifications automatically at login:

```bash
./productivity-agent install-service
```

Remove the background service with `./productivity-agent uninstall-service`. Logs are written to `~/Library/Logs/ProductivityAgent.log`.

## Optional API and AI planning extension

Install the optional API packages and start the service:

```bash
python3 -m pip install -e '.[api]'
./productivity-agent api
```

Interactive API documentation is then available at `http://127.0.0.1:8000/docs`. The API exposes health, tasks, status changes, and daily plan creation/retrieval.

`planner.py` defines a `PlanningProvider` contract and includes an offline deterministic provider. A future OpenAI or other LLM adapter can implement that contract to suggest task breakdowns; the deterministic scheduler remains authoritative for time windows, conflicts, and persistence.

## Scheduling behavior

The planner considers pending tasks plus unfinished tasks already scheduled for the day being regenerated. It sorts them by:

1. priority: high, medium, low;
2. earliest deadline (tasks without deadlines come last within their priority);
3. task ID, which provides stable creation order.

Each task is placed sequentially if its entire estimated duration fits. If one task does not fit, the engine continues checking later tasks, so a shorter task can use the remaining window. Regenerating a plan replaces that day's sessions atomically while preserving completed and skipped task states.

## Project structure

```text
src/productivity_agent/
├── models.py          Domain types
├── storage.py         SQLite repository and schema
├── scheduler.py       Pure deterministic planning logic
├── notifications.py   macOS notification adapter and watcher
├── service.py         macOS background service installer
├── webapp.py          Dependency-free local browser dashboard
├── desktop.py         Optional Tk dashboard (not used on incompatible macOS Tcl builds)
├── api.py             Optional FastAPI adapter
├── planner.py         AI planning provider contract
└── cli.py             Command-line adapter
tests/                 Built-in unittest suite
```

The dependency direction is intentional: the scheduler works on domain models without knowing about SQLite or the CLI. A future FastAPI layer can call the repository and scheduler directly, while an LLM component can propose task breakdowns or priorities without controlling time arithmetic or database transactions.

## Run tests

No test package installation is needed:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Current scope

This version uses local naive date/time values and schedules tasks as complete blocks. The desktop UI currently creates one or more windows for today; advanced dates and deadline editing remain available in the CLI. LLM task suggestions are intentionally an extension point rather than being allowed to perform deterministic scheduling or database transactions.
