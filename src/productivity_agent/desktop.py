"""Native Tkinter desktop dashboard."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, time
from tkinter import messagebox, ttk

from .cli import default_database_path
from .models import Priority, Recurrence, TaskStatus
from .scheduler import build_plan_windows
from .storage import Repository


class ProductivityApp(tk.Tk):
    def __init__(self, repository: Repository | None = None):
        super().__init__()
        self.repository = repository or Repository(default_database_path())
        self.repository.initialize()
        self.title("Personal AI Productivity Agent")
        self.geometry("980x680")
        self.minsize(820, 560)
        self._build()
        self.refresh()

    def _build(self):
        header = ttk.Frame(self, padding=16)
        header.pack(fill="x")
        ttk.Label(header, text="Today", font=("Helvetica", 24, "bold")).pack(side="left")
        self.summary = ttk.Label(header)
        self.summary.pack(side="right")

        form = ttk.LabelFrame(self, text="Add task", padding=12)
        form.pack(fill="x", padx=16)
        self.title_value = tk.StringVar()
        self.minutes_value = tk.StringVar(value="30")
        self.priority_value = tk.StringVar(value="medium")
        self.repeat_value = tk.StringVar(value="none")
        ttk.Entry(form, textvariable=self.title_value, width=42).grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Combobox(form, textvariable=self.priority_value, values=[p.value for p in Priority], width=9, state="readonly").grid(row=0, column=1, padx=4)
        ttk.Entry(form, textvariable=self.minutes_value, width=7).grid(row=0, column=2, padx=4)
        ttk.Combobox(form, textvariable=self.repeat_value, values=[r.value for r in Recurrence], width=9, state="readonly").grid(row=0, column=3, padx=4)
        ttk.Button(form, text="Add", command=self.add_task).grid(row=0, column=4, padx=4)
        form.columnconfigure(0, weight=1)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=16, pady=12)
        tasks_frame = ttk.LabelFrame(body, text="Tasks", padding=8)
        plan_frame = ttk.LabelFrame(body, text="Daily plan", padding=8)
        body.add(tasks_frame, weight=3)
        body.add(plan_frame, weight=2)
        self.tasks = ttk.Treeview(tasks_frame, columns=("priority", "minutes", "status", "repeat"), show="tree headings")
        self.tasks.heading("#0", text="Task")
        for key, label, width in (("priority", "Priority", 75), ("minutes", "Minutes", 65), ("status", "Status", 85), ("repeat", "Repeat", 70)):
            self.tasks.heading(key, text=label); self.tasks.column(key, width=width, anchor="center")
        self.tasks.pack(fill="both", expand=True)
        actions = ttk.Frame(tasks_frame); actions.pack(fill="x", pady=(8, 0))
        for label, command in (("Complete", lambda: self.set_status(TaskStatus.COMPLETED)),
                               ("Skip", lambda: self.set_status(TaskStatus.SKIPPED)),
                               ("Reopen", self.reopen), ("Delete", self.delete)):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=2)

        settings = ttk.Frame(plan_frame); settings.pack(fill="x")
        self.windows_value = tk.StringVar(value="09:00-12:00,13:00-17:00")
        self.break_value = tk.StringVar(value="10")
        ttk.Label(settings, text="Windows").grid(row=0, column=0)
        ttk.Entry(settings, textvariable=self.windows_value, width=25).grid(row=0, column=1)
        ttk.Label(settings, text="Break").grid(row=0, column=2); ttk.Entry(settings, textvariable=self.break_value, width=4).grid(row=0, column=3)
        ttk.Button(settings, text="Generate", command=self.generate).grid(row=0, column=4, padx=4)
        self.plan = tk.Listbox(plan_frame, font=("Menlo", 12), activestyle="none")
        self.plan.pack(fill="both", expand=True, pady=(8, 0))

    def selected_id(self) -> int:
        selected = self.tasks.selection()
        if not selected:
            raise ValueError("Select a task first")
        return int(selected[0])

    def perform(self, action):
        try: action()
        except Exception as error: messagebox.showerror("Productivity Agent", str(error))
        self.refresh()

    def add_task(self):
        def action():
            self.repository.add_task(self.title_value.get(), Priority(self.priority_value.get()),
                                     int(self.minutes_value.get()), recurrence=Recurrence(self.repeat_value.get()))
            self.title_value.set("")
        self.perform(action)

    def set_status(self, status): self.perform(lambda: self.repository.set_task_status(self.selected_id(), status))
    def reopen(self): self.perform(lambda: self.repository.reopen_task(self.selected_id()))
    def delete(self): self.perform(lambda: self.repository.delete_task(self.selected_id()))

    def generate(self):
        def action():
            today = date.today()
            windows = []
            for value in self.windows_value.get().split(","):
                start_text, end_text = value.strip().split("-", 1)
                windows.append((datetime.combine(today, time.fromisoformat(start_text)),
                                datetime.combine(today, time.fromisoformat(end_text))))
            slots = build_plan_windows(self.repository.tasks_for_planning(today), windows, int(self.break_value.get()))
            self.repository.save_availability(today, windows)
            self.repository.replace_schedule(today, windows[0][0], windows[-1][1], slots)
        self.perform(action)

    def refresh(self):
        for item in self.tasks.get_children(): self.tasks.delete(item)
        tasks = self.repository.list_tasks()
        for task in tasks:
            self.tasks.insert("", "end", iid=str(task.id), text=task.title,
                              values=(task.priority.value, task.minutes_to_schedule, task.status.value, task.recurrence.value))
        active = sum(task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED) for task in tasks)
        self.summary.config(text=f"{active} active · {len(tasks)} total")
        self.plan.delete(0, "end")
        schedule = self.repository.get_schedule(date.today())
        if schedule:
            for item in schedule.items:
                self.plan.insert("end", f"{item.start_at:%H:%M}–{item.end_at:%H:%M}  {item.title}")
        else: self.plan.insert("end", "No plan generated for today")


def main():
    ProductivityApp().mainloop()


if __name__ == "__main__": main()
