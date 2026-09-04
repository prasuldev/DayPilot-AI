"""Install/uninstall a per-user macOS LaunchAgent for notifications."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


LABEL = "com.local.productivity-agent.notifications"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install_notification_service(launcher: Path, database: Path) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("Background notification service is supported on macOS only")
    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    runtime = database.expanduser().parent / "runtime"
    source_package = launcher.resolve().parent / "src" / "productivity_agent"
    if runtime.exists():
        shutil.rmtree(runtime)
    shutil.copytree(source_package, runtime / "productivity_agent")
    payload = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "productivity_agent", "--db", str(database.expanduser()),
                             "notifications", "--interval", "30"],
        "EnvironmentVariables": {"PYTHONPATH": str(runtime)},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "ProductivityAgent.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "ProductivityAgent.log"),
    }
    with target.open("wb") as handle:
        plistlib.dump(payload, handle)
    subprocess.run(["launchctl", "bootout", f"gui/{__import__('os').getuid()}", str(target)], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "bootstrap", f"gui/{__import__('os').getuid()}", str(target)], check=True)
    return target


def uninstall_notification_service() -> None:
    target = plist_path()
    if target.exists():
        subprocess.run(["launchctl", "bootout", f"gui/{__import__('os').getuid()}", str(target)], check=False)
        target.unlink()
