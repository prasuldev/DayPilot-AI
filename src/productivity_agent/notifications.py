"""macOS notification delivery and schedule watching."""

from __future__ import annotations

import platform
import subprocess
import time
from datetime import datetime
from typing import Callable

from .storage import Repository


APPLE_SCRIPT = """
on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run
"""


def send_macos_notification(title: str, message: str) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Desktop notifications are supported on macOS only")
    subprocess.run(["osascript", "-e", APPLE_SCRIPT, title, message], check=True)


def process_notifications(
    repository: Repository,
    now: datetime | None = None,
    upcoming_minutes: int = 10,
    sender: Callable[[str, str], None] = send_macos_notification,
) -> int:
    events = repository.claim_notification_events(now or datetime.now(), upcoming_minutes)
    for title, message in events:
        sender(title, message)
    return len(events)


def watch_notifications(repository: Repository, upcoming_minutes: int = 10, interval_seconds: int = 30) -> None:
    try:
        while True:
            process_notifications(repository, upcoming_minutes=upcoming_minutes)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        return
