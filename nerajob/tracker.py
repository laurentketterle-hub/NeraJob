"""Application tracker — status states for applied/interview/offer (closes #40)."""
from datetime import datetime
from enum import Enum
from typing import Optional
import json, os

class AppStatus(str, Enum):
    APPLIED = "applied"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    TECHNICAL = "technical"
    ONSITE = "onsite"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

STATUS_TRANSITIONS = {
    AppStatus.APPLIED: [AppStatus.PHONE_SCREEN, AppStatus.REJECTED, AppStatus.WITHDRAWN],
    AppStatus.PHONE_SCREEN: [AppStatus.INTERVIEW, AppStatus.REJECTED, AppStatus.WITHDRAWN],
    AppStatus.INTERVIEW: [AppStatus.TECHNICAL, AppStatus.ONSITE, AppStatus.REJECTED, AppStatus.WITHDRAWN],
    AppStatus.TECHNICAL: [AppStatus.ONSITE, AppStatus.OFFER, AppStatus.REJECTED, AppStatus.WITHDRAWN],
    AppStatus.ONSITE: [AppStatus.OFFER, AppStatus.REJECTED, AppStatus.WITHDRAWN],
    AppStatus.OFFER: [AppStatus.ACCEPTED, AppStatus.REJECTED, AppStatus.WITHDRAWN],
    AppStatus.ACCEPTED: [],
    AppStatus.REJECTED: [],
    AppStatus.WITHDRAWN: [],
}

class Application:
    def __init__(self, company: str, role: str, url: str = ""):
        self.id = f"{company}-{role}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.company = company
        self.role = role
        self.url = url
        self.status = AppStatus.APPLIED
        self.notes: list[str] = []
        self.dates: dict[str, str] = {"applied": datetime.now().isoformat()}
    
    def transition(self, new_status: AppStatus, note: str = "") -> bool:
        if new_status not in STATUS_TRANSITIONS.get(self.status, []):
            return False
        self.status = new_status
        self.dates[new_status.value] = datetime.now().isoformat()
        if note:
            self.notes.append(f"[{new_status.value}] {note}")
        return True
    
    def to_dict(self) -> dict:
        return {
            "id": self.id, "company": self.company, "role": self.role,
            "url": self.url, "status": self.status.value,
            "notes": self.notes, "dates": self.dates
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Application":
        app = cls(data["company"], data["role"], data.get("url", ""))
        app.id = data.get("id", app.id)
        app.status = AppStatus(data["status"])
        app.notes = data.get("notes", [])
        app.dates = data.get("dates", {})
        return app


class Tracker:
    def __init__(self, path: str = "applications.json"):
        self.path = path
        self.apps: dict[str, Application] = {}
        self._load()
    
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                data = json.load(f)
            self.apps = {k: Application.from_dict(v) for k, v in data.items()}
    
    def _save(self):
        with open(self.path, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.apps.items()}, f, indent=2, default=str)
    
    def add(self, company: str, role: str, url: str = "") -> Application:
        app = Application(company, role, url)
        self.apps[app.id] = app
        self._save()
        return app
    
    def update(self, app_id: str, new_status: AppStatus, note: str = "") -> bool:
        app = self.apps.get(app_id)
        if not app:
            return False
        ok = app.transition(new_status, note)
        if ok:
            self._save()
        return ok
    
    def list(self, status: Optional[AppStatus] = None) -> list[Application]:
        apps = list(self.apps.values())
        if status:
            apps = [a for a in apps if a.status == status]
        return sorted(apps, key=lambda a: a.dates.get("applied", ""), reverse=True)
    
    def stats(self) -> dict:
        counts = {s.value: 0 for s in AppStatus}
        for app in self.apps.values():
            counts[app.status.value] += 1
        total = len(self.apps)
        active = total - counts["rejected"] - counts["withdrawn"]
        return {"total": total, "active": active, "by_status": counts}


def cli():
    import argparse
    parser = argparse.ArgumentParser(description="NeraJob Application Tracker")
    sub = parser.add_subparsers(dest="cmd")
    
    add_p = sub.add_parser("add")
    add_p.add_argument("company")
    add_p.add_argument("role")
    add_p.add_argument("--url", default="")
    
    list_p = sub.add_parser("list")
    list_p.add_argument("--status", choices=[s.value for s in AppStatus], default=None)
    
    update_p = sub.add_parser("update")
    update_p.add_argument("app_id")
    update_p.add_argument("status", choices=[s.value for s in AppStatus])
    update_p.add_argument("--note", default="")
    
    sub.add_parser("stats")
    
    args = parser.parse_args()
    tracker = Tracker()
    
    if args.cmd == "add":
        app = tracker.add(args.company, args.role, args.url)
        print(f"Added: {app.id} ({app.company} - {app.role})")
    elif args.cmd == "list":
        status = AppStatus(args.status) if args.status else None
        apps = tracker.list(status)
        for a in apps:
            print(f"[{a.status.value}] {a.company} — {a.role} ({a.id[:20]}...)")
    elif args.cmd == "update":
        ok = tracker.update(args.app_id, AppStatus(args.status), args.note)
        print("OK" if ok else f"App {args.app_id} not found or invalid transition")
    elif args.cmd == "stats":
        s = tracker.stats()
        print(f"Total: {s['total']} | Active: {s['active']}")
        for st, cnt in sorted(s['by_status'].items()):
            if cnt > 0:
                print(f"  {st}: {cnt}")
    else:
        parser.print_help()

if __name__ == "__main__":
    cli()
