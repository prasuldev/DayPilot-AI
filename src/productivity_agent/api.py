"""Optional FastAPI adapter. Install with `pip install fastapi uvicorn`."""



from datetime import date, datetime
from pathlib import Path

from .models import Priority, Recurrence, TaskStatus
from .scheduler import build_plan_windows
from .storage import Repository


def create_app(database_path: str | Path):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as error:
        raise RuntimeError("Install API support with: pip install fastapi uvicorn") from error

    repository = Repository(database_path)
    repository.initialize()
    app = FastAPI(title="Personal AI Productivity Agent", version="0.2.0")

    class TaskInput(BaseModel):
        title: str
        priority: str = "medium"
        estimated_minutes: int
        deadline: datetime | None = None
        goal_id: int | None = None
        recurrence: str = "none"

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/tasks")
    def tasks():
        return [task.__dict__ for task in repository.list_tasks()]

    @app.post("/tasks", status_code=201)
    def add_task(payload: TaskInput):
        try:
            return repository.add_task(payload.title, Priority(payload.priority), payload.estimated_minutes,
                                       payload.deadline, payload.goal_id, Recurrence(payload.recurrence)).__dict__
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.patch("/tasks/{task_id}/status")
    def set_status(task_id: int, status: str):
        try:
            repository.set_task_status(task_id, TaskStatus(status))
            return {"task_id": task_id, "status": status}
        except ValueError as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/plans/{plan_date}")
    def plan(plan_date: date):
        saved = repository.get_schedule(plan_date)
        if not saved:
            raise HTTPException(404, "No plan for this date")
        return {"date": plan_date, "items": [item.__dict__ for item in saved.items]}

    @app.post("/plans/{plan_date}")
    def generate(plan_date: date, start: str = "09:00", end: str = "17:00", break_minutes: int = 0):
        try:
            work_start = datetime.fromisoformat(f"{plan_date}T{start}")
            work_end = datetime.fromisoformat(f"{plan_date}T{end}")
            slots = build_plan_windows(repository.tasks_for_planning(plan_date), [(work_start, work_end)], break_minutes)
            saved = repository.replace_schedule(plan_date, work_start, work_end, slots)
            return {"date": plan_date, "items": [item.__dict__ for item in saved.items]}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
    return app
