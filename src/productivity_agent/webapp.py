"""Dependency-free local dashboard served only on the loopback interface."""

from __future__ import annotations

import html
import threading
import webbrowser
from datetime import date, datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .cli import default_database_path
from .models import Priority, Recurrence, TaskStatus
from .scheduler import build_plan_windows
from .storage import Repository


STYLE = """
:root{--bg:#f5f7fb;--panel:#fff;--text:#172033;--muted:#697386;--line:#e6eaf2;--primary:#5b5ce2;--primary2:#7c6ff0;--soft:#f0efff;--shadow:0 12px 32px rgba(25,32,56,.08)}
*{box-sizing:border-box}body{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);margin:0;min-height:100vh}
.shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}.sidebar{background:#17182a;color:#fff;padding:28px 20px;position:sticky;top:0;height:100vh}.brand{display:flex;align-items:center;gap:11px;font-weight:750;font-size:18px;margin-bottom:38px}.logo{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,#7c6ff0,#55c2ff);display:grid;place-items:center;font-size:20px;box-shadow:0 8px 22px #5b5ce266}.nav{display:flex;flex-direction:column;gap:8px}.nav a{color:#aeb2c7;text-decoration:none;padding:12px 14px;border-radius:10px;font-size:14px}.nav a.active{background:#292a43;color:#fff}.privacy{position:absolute;bottom:26px;left:20px;right:20px;color:#8f94aa;font-size:12px;line-height:1.5}.dot{width:7px;height:7px;background:#55d98b;border-radius:50%;display:inline-block;margin-right:7px}
main{padding:34px 42px;max-width:1440px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px}.top h1{margin:0;font-size:28px;letter-spacing:-.5px}.sub{color:var(--muted);margin:6px 0 0;font-size:14px}.date-chip{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px;color:var(--muted);font-size:13px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}.stat{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:17px 18px;box-shadow:0 4px 18px rgba(25,32,56,.035)}.stat span{color:var(--muted);font-size:12px;font-weight:650;text-transform:uppercase;letter-spacing:.6px}.stat strong{display:block;font-size:25px;margin-top:7px}.stat.primary{background:linear-gradient(135deg,var(--primary),var(--primary2));color:white;border:0}.stat.primary span{color:#e8e7ff}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:var(--shadow)}.quick{margin-bottom:20px}.card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.card-head h2{margin:0;font-size:17px}.hint{color:var(--muted);font-size:12px}
.add-grid{display:grid;grid-template-columns:minmax(240px,2fr) 115px 105px 120px minmax(155px,1fr) auto;gap:9px}label{font-size:12px;font-weight:650;color:#525b6f;display:block;margin-bottom:6px}input,select,button{font:inherit}input,select{width:100%;border:1px solid #dbe0ea;background:#fafbfe;border-radius:10px;padding:10px 11px;color:var(--text);outline:none}input:focus,select:focus{border-color:var(--primary);box-shadow:0 0 0 3px #5b5ce21c}.button-wrap{display:flex;align-items:flex-end}button{border:0;border-radius:10px;padding:10px 14px;background:var(--primary);color:white;font-weight:650;cursor:pointer;transition:.18s ease}button:hover{transform:translateY(-1px);filter:brightness(1.04)}button:focus-visible{outline:3px solid #5b5ce244}.add-button{height:41px;min-width:108px}
.content{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.8fr);gap:20px}.toolbar{display:flex;gap:8px;align-items:center}.search{max-width:210px;padding:8px 10px}.filters{display:flex;gap:6px}.filter{background:#f4f5f9;color:#687086;padding:7px 10px;font-size:12px}.filter.active{background:var(--soft);color:var(--primary)}
.task-list{display:flex;flex-direction:column;gap:9px}.task{display:grid;grid-template-columns:38px minmax(150px,1fr) auto auto;gap:12px;align-items:center;border:1px solid var(--line);border-radius:13px;padding:12px;transition:.15s}.task:hover{border-color:#cfd4e5;box-shadow:0 5px 16px rgba(25,32,56,.06)}.task.done{opacity:.62}.task-check form{margin:0}.check{width:28px;height:28px;border-radius:9px;padding:0;background:#eef0f6;color:#939aab}.done .check{background:#dff7e9;color:#21985a}.task-title{font-weight:650;font-size:14px;margin-bottom:5px}.task.done .task-title{text-decoration:line-through}.meta{display:flex;gap:7px;align-items:center;color:var(--muted);font-size:12px}.badge{border-radius:999px;padding:3px 8px;font-weight:650}.priority-high{background:#ffe8e8;color:#c53f47}.priority-medium{background:#fff2d8;color:#9d6914}.priority-low{background:#e7f5ee;color:#277a54}.status{background:#eef1f7;color:#606a7d}.task-actions{display:flex;gap:4px}.task-actions form{margin:0}.icon-btn{background:transparent;color:#778095;padding:7px 8px;font-size:12px}.icon-btn:hover{background:#f1f2f7;transform:none}.icon-btn.danger:hover{background:#fff0f0;color:#c53f47}.empty{text-align:center;padding:46px 20px;color:var(--muted)}.empty-icon{font-size:34px;margin-bottom:10px}
.planner-form{display:grid;grid-template-columns:1fr 72px;gap:9px;margin-bottom:18px}.planner-form .wide{grid-column:1/-1}.planner-form button{grid-column:1/-1}.timeline{position:relative;padding-left:12px}.slot{display:grid;grid-template-columns:58px 1fr;gap:12px;position:relative;padding-bottom:18px}.slot:before{content:"";position:absolute;left:65px;top:8px;width:9px;height:9px;border-radius:50%;background:var(--primary);box-shadow:0 0 0 4px var(--soft)}.slot:not(:last-child):after{content:"";position:absolute;left:69px;top:19px;bottom:0;width:1px;background:#dfe2f2}.slot-time{font-size:12px;color:var(--muted);padding-top:3px}.slot-card{margin-left:12px;background:#f8f8ff;border:1px solid #e6e4ff;border-radius:11px;padding:11px 12px}.slot-title{font-weight:650;font-size:13px}.slot-duration{font-size:11px;color:var(--muted);margin-top:4px}.plan-empty{background:#fafbfe;border:1px dashed #d8deea;border-radius:12px;padding:28px 15px;text-align:center;color:var(--muted);font-size:13px}
.mobile-brand{display:none}@media(max-width:1050px){.add-grid{grid-template-columns:2fr 1fr 1fr}.button-wrap{align-items:end}.content{grid-template-columns:1fr}.planner{order:-1}}@media(max-width:720px){.shell{display:block}.sidebar{display:none}main{padding:22px 16px}.mobile-brand{display:flex;margin-bottom:20px}.top{align-items:flex-start}.date-chip{display:none}.stats{grid-template-columns:repeat(2,1fr)}.add-grid{grid-template-columns:1fr 1fr}.title-field,.deadline-field,.button-wrap{grid-column:1/-1}.add-button{width:100%}.card{padding:16px}.card-head{align-items:flex-start;gap:10px;flex-direction:column}.toolbar{width:100%;flex-wrap:wrap}.search{max-width:none}.task{grid-template-columns:34px 1fr}.task-actions{grid-column:2}.status-cell{display:none}}
"""


class DashboardHandler(BaseHTTPRequestHandler):
    repository: Repository

    def log_message(self, format, *args):
        return

    def redirect(self):
        self.send_response(303); self.send_header("Location", "/"); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = {key: values[0] for key, values in parse_qs(self.rfile.read(length).decode()).items()}
        path = urlparse(self.path).path
        try:
            if path == "/tasks":
                deadline = datetime.fromisoformat(data["deadline"] + "T23:59") if data.get("deadline") else None
                self.repository.add_task(data["title"], Priority(data["priority"]), int(data["minutes"]), deadline,
                                         recurrence=Recurrence(data.get("repeat", "none")))
            elif path.startswith("/tasks/"):
                _, _, task_id, action = path.split("/")
                if action == "complete": self.repository.set_task_status(int(task_id), TaskStatus.COMPLETED)
                elif action == "skip": self.repository.set_task_status(int(task_id), TaskStatus.SKIPPED)
                elif action == "reopen": self.repository.reopen_task(int(task_id))
                elif action == "delete": self.repository.delete_task(int(task_id))
            elif path == "/generate":
                today = date.today(); windows = []
                for value in data["windows"].split(","):
                    start, end = value.strip().split("-", 1)
                    windows.append((datetime.combine(today, time.fromisoformat(start)), datetime.combine(today, time.fromisoformat(end))))
                slots = build_plan_windows(self.repository.tasks_for_planning(today), windows, int(data["break_minutes"]))
                self.repository.save_availability(today, windows)
                self.repository.replace_schedule(today, windows[0][0], windows[-1][1], slots)
        except (ValueError, KeyError) as error:
            self.send_error(400, str(error)); return
        self.redirect()

    def do_GET(self):
        if urlparse(self.path).path != "/": self.send_error(404); return
        tasks = self.repository.list_tasks(); schedule = self.repository.get_schedule(date.today())
        task_cards = "".join(self.task_card(task) for task in tasks) or '<div class="empty"><div class="empty-icon">✓</div><b>Your task list is clear</b><p>Add a task above to start planning.</p></div>'
        slots = "".join(self.slot_card(item) for item in schedule.items) if schedule and schedule.items else '<div class="plan-empty">No sessions planned yet.<br>Add active tasks and generate your day.</div>'
        active = sum(task.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED) for task in tasks)
        completed = sum(task.status is TaskStatus.COMPLETED for task in tasks)
        scheduled = sum(task.status is TaskStatus.SCHEDULED for task in tasks)
        focus_minutes = sum(item.end_at.minute - item.start_at.minute + 60 * (item.end_at.hour - item.start_at.hour) for item in schedule.items) if schedule else 0
        page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Productivity Agent</title><style>{STYLE}</style></head>
<body><div class="shell"><aside class="sidebar"><div class="brand"><div class="logo">✦</div><span>FocusFlow</span></div><nav class="nav"><a class="active" href="#">▦ &nbsp; Today</a><a href="#tasks">✓ &nbsp; My tasks</a><a href="#planner">◷ &nbsp; Planner</a></nav><div class="privacy"><span class="dot"></span>Running privately<br>All data stays on this Mac</div></aside>
<main><div class="brand mobile-brand"><div class="logo">✦</div><span>FocusFlow</span></div><header class="top"><div><h1>Good day 👋</h1><p class="sub">Here’s a clear view of what matters today.</p></div><div class="date-chip">{date.today():%A · %d %B %Y}</div></header>
<section class="stats"><div class="stat primary"><span>Active tasks</span><strong>{active}</strong></div><div class="stat"><span>Scheduled</span><strong>{scheduled}</strong></div><div class="stat"><span>Completed</span><strong>{completed}</strong></div><div class="stat"><span>Focus time</span><strong>{focus_minutes // 60}h {focus_minutes % 60}m</strong></div></section>
<section class="card quick"><div class="card-head"><div><h2>Quick add</h2><span class="hint">Capture something before you forget it</span></div></div><form method="post" action="/tasks" class="add-grid"><div class="title-field"><label>Task name</label><input name="title" placeholder="e.g. Practice Python for interview" required autofocus></div><div><label>Priority</label><select name="priority"><option value="high">High</option><option value="medium" selected>Medium</option><option value="low">Low</option></select></div><div><label>Duration</label><select name="minutes"><option value="15">15 min</option><option value="30" selected>30 min</option><option value="45">45 min</option><option value="60">1 hour</option><option value="90">1.5 hours</option></select></div><div><label>Repeat</label><select name="repeat"><option value="none">Doesn’t repeat</option><option value="daily">Every day</option><option value="weekly">Every week</option></select></div><div class="deadline-field"><label>Deadline (optional)</label><input name="deadline" type="date"></div><div class="button-wrap"><button class="add-button">＋ Add task</button></div></form></section>
<div class="content"><section class="card" id="tasks"><div class="card-head"><div><h2>My tasks</h2><span class="hint">{len(tasks)} tasks in total</span></div><div class="toolbar"><input id="search" class="search" placeholder="Search tasks…" aria-label="Search tasks"><div class="filters"><button class="filter active" data-filter="all">All</button><button class="filter" data-filter="pending">Active</button><button class="filter" data-filter="completed">Done</button></div></div></div><div class="task-list" id="task-list">{task_cards}</div></section>
<section class="card planner" id="planner"><div class="card-head"><div><h2>Today’s plan</h2><span class="hint">Build a realistic focus schedule</span></div></div><form method="post" action="/generate" class="planner-form"><div class="wide"><label>Available time windows</label><input name="windows" value="09:00-12:00,13:00-17:00" aria-label="Available time windows"></div><div><label>Break</label><input name="break_minutes" type="number" min="0" value="10"></div><div style="align-self:end;color:var(--muted);font-size:12px;padding-bottom:11px">minutes</div><button>✦ Generate my day</button></form><div class="timeline">{slots}</div></section></div></main></div>
<script>const q=document.querySelector('#search'),cards=[...document.querySelectorAll('.task')],filters=[...document.querySelectorAll('.filter')];let filter='all';function update(){{const term=(q?.value||'').toLowerCase();cards.forEach(c=>{{const status=c.dataset.status;const matchesFilter=filter==='all'||(filter==='pending'?(status==='pending'||status==='scheduled'):status===filter);c.style.display=matchesFilter&&c.dataset.title.includes(term)?'grid':'none'}})}}q?.addEventListener('input',update);filters.forEach(b=>b.addEventListener('click',e=>{{e.preventDefault();filters.forEach(x=>x.classList.remove('active'));b.classList.add('active');filter=b.dataset.filter;update()}}));</script></body></html>"""
        encoded = page.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)

    @staticmethod
    def task_card(task):
        title = html.escape(task.title)
        done = task.status is TaskStatus.COMPLETED
        primary_action = "reopen" if done else "complete"
        primary_label = "↻" if done else "✓"
        repeat = f" · {task.recurrence.value}" if task.recurrence is not Recurrence.NONE else ""
        deadline = f" · due {task.deadline:%d %b}" if task.deadline else ""
        return f'''<article class="task {'done' if done else ''}" data-status="{task.status.value}" data-title="{title.lower()}"><div class="task-check"><form method="post" action="/tasks/{task.id}/{primary_action}"><button class="check" title="{'Reopen task' if done else 'Mark complete'}">{primary_label}</button></form></div><div><div class="task-title">{title}</div><div class="meta"><span class="badge priority-{task.priority.value}">{task.priority.value.title()}</span><span>{task.minutes_to_schedule} min{repeat}{deadline}</span></div></div><div class="status-cell"><span class="badge status">{task.status.value.title()}</span></div><div class="task-actions">{'' if done else f'<form method="post" action="/tasks/{task.id}/skip"><button class="icon-btn" title="Skip for now">Skip</button></form>'}<form method="post" action="/tasks/{task.id}/delete" onsubmit="return confirm('Delete this task?')"><button class="icon-btn danger" title="Delete task">Delete</button></form></div></article>'''

    @staticmethod
    def slot_card(item):
        minutes = int((item.end_at - item.start_at).total_seconds() // 60)
        return f'<div class="slot"><div class="slot-time">{item.start_at:%H:%M}</div><div class="slot-card"><div class="slot-title">{html.escape(item.title)}</div><div class="slot-duration">{minutes} min · ends {item.end_at:%H:%M}</div></div></div>'


def main():
    repository = Repository(default_database_path()); repository.initialize()
    DashboardHandler.repository = repository
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8765), DashboardHandler)
    except OSError as error:
        raise RuntimeError("Could not start the dashboard on port 8765. Close another running copy and try again.") from error
    threading.Timer(0.4, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    print("Productivity Agent is running at http://127.0.0.1:8765 — press Ctrl-C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
