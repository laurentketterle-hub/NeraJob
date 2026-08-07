"""Application tracker for NeraJob — manage job applications through a state machine."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AppStatus(str, Enum):
    APPLIED = "applied"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# Valid transitions
_TRANSITIONS: dict[AppStatus, set[AppStatus]] = {
    AppStatus.APPLIED: {AppStatus.PHONE_SCREEN, AppStatus.REJECTED},
    AppStatus.PHONE_SCREEN: {AppStatus.INTERVIEW, AppStatus.REJECTED},
    AppStatus.INTERVIEW: {AppStatus.OFFER, AppStatus.REJECTED},
    AppStatus.OFFER: {AppStatus.ACCEPTED, AppStatus.REJECTED},
    AppStatus.ACCEPTED: set(),
    AppStatus.REJECTED: set(),
}


@dataclass
class Application:
    company: str
    role: str
    id: str = ""
    status: AppStatus = AppStatus.APPLIED
    notes: str = ""

    def transition(self, new_status: AppStatus) -> bool:
        if new_status in _TRANSITIONS.get(self.status, set()):
            self.status = new_status
            return True
        return False


class Tracker:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            path = Path.home() / ".nerajob" / "tracker.json"
        self.path = Path(path) if isinstance(path, str) else path
        self.apps: dict[str, Application] = {}
        self._counter = 0
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._counter = data.get("_counter", 0)
            for raw in data.get("apps", []):
                app = Application(
                    company=raw["company"],
                    role=raw["role"],
                    id=raw["id"],
                    status=AppStatus(raw.get("status", "applied")),
                    notes=raw.get("notes", ""),
                )
                self.apps[app.id] = app
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "_counter": self._counter,
            "apps": [
                {
                    "company": a.company,
                    "role": a.role,
                    "id": a.id,
                    "status": a.status.value,
                    "notes": a.notes,
                }
                for a in self.apps.values()
            ],
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, company: str, role: str) -> Application:
        self._counter += 1
        app = Application(company=company, role=role, id=str(self._counter))
        self.apps[app.id] = app
        self._save()
        return app

    def update(self, app_id: str, status: AppStatus, notes: str = "") -> bool:
        app = self.apps.get(app_id)
        if app is None:
            return False
        app.status = status
        if notes:
            app.notes = notes
        self._save()
        return True

    def list(self, status: AppStatus | None = None) -> list[Application]:
        apps = list(self.apps.values())
        if status is not None:
            apps = [a for a in apps if a.status == status]
        return apps

    def stats(self) -> dict[str, Any]:
        all_apps = list(self.apps.values())
        active = [a for a in all_apps if a.status != AppStatus.REJECTED]
        by_status: dict[str, int] = {}
        for a in all_apps:
            key = a.status.value
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "total": len(all_apps),
            "active": len(active),
            "by_status": by_status,
        }


def cli() -> None:
    """Simple CLI for tracker (used by test_cli_help)."""
    print("NeraJob Tracker CLI")
    print("Usage: tracker [command]")
    print("Commands: add, list, stats, update")
