"""
Application tracker with status states for NeraJob.
Tracks job applications through a complete lifecycle with state transitions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
import json


class ApplicationStatus(Enum):
    """Complete application lifecycle states."""
    SAVED = "saved"               # Draft, not yet submitted
    APPLIED = "applied"           # Application submitted
    SCREENING = "screening"       # Initial screening / ATS review
    PHONE_SCREEN = "phone_screen" # Phone/video screening call
    INTERVIEW = "interview"       # Technical/team interview
    FINAL_INTERVIEW = "final"     # Final round interview
    OFFER = "offer"               # Offer received
    NEGOTIATING = "negotiating"   # Negotiating terms
    ACCEPTED = "accepted"         # Offer accepted
    DECLINED = "declined"         # Declined by candidate
    REJECTED = "rejected"         # Rejected by employer
    WITHDRAWN = "withdrawn"       # Withdrawn by candidate
    EXPIRED = "expired"           # Posting expired/no response
    ARCHIVED = "archived"         # Archived for record-keeping

    @classmethod
    def active_states(cls) -> list:
        """States where the application is still active."""
        return [
            cls.SAVED, cls.APPLIED, cls.SCREENING, cls.PHONE_SCREEN,
            cls.INTERVIEW, cls.FINAL_INTERVIEW, cls.OFFER, cls.NEGOTIATING
        ]

    @classmethod
    def terminal_states(cls) -> list:
        """States where the application process has ended."""
        return [cls.ACCEPTED, cls.DECLINED, cls.REJECTED, cls.WITHDRAWN, cls.EXPIRED]


# Valid state transitions
VALID_TRANSITIONS: Dict[ApplicationStatus, List[ApplicationStatus]] = {
    ApplicationStatus.SAVED: [ApplicationStatus.APPLIED, ApplicationStatus.ARCHIVED, ApplicationStatus.WITHDRAWN],
    ApplicationStatus.APPLIED: [ApplicationStatus.SCREENING, ApplicationStatus.REJECTED, ApplicationStatus.EXPIRED, ApplicationStatus.WITHDRAWN],
    ApplicationStatus.SCREENING: [ApplicationStatus.PHONE_SCREEN, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
    ApplicationStatus.PHONE_SCREEN: [ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
    ApplicationStatus.INTERVIEW: [ApplicationStatus.FINAL_INTERVIEW, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
    ApplicationStatus.FINAL_INTERVIEW: [ApplicationStatus.OFFER, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
    ApplicationStatus.OFFER: [ApplicationStatus.NEGOTIATING, ApplicationStatus.ACCEPTED, ApplicationStatus.DECLINED],
    ApplicationStatus.NEGOTIATING: [ApplicationStatus.ACCEPTED, ApplicationStatus.DECLINED],
    ApplicationStatus.ACCEPTED: [ApplicationStatus.ARCHIVED],
    ApplicationStatus.DECLINED: [ApplicationStatus.ARCHIVED],
    ApplicationStatus.REJECTED: [ApplicationStatus.ARCHIVED],
    ApplicationStatus.WITHDRAWN: [ApplicationStatus.ARCHIVED],
    ApplicationStatus.EXPIRED: [ApplicationStatus.ARCHIVED],
    ApplicationStatus.ARCHIVED: [],
}


@dataclass
class StatusEvent:
    """A single status change event in the application timeline."""
    from_status: ApplicationStatus
    to_status: ApplicationStatus
    timestamp: str
    note: str = ""


@dataclass
class Application:
    """Tracks a single job application through its lifecycle."""
    id: str
    job_id: str
    job_title: str
    company: str
    status: ApplicationStatus = ApplicationStatus.SAVED
    applied_date: Optional[str] = None
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    history: List[StatusEvent] = field(default_factory=list)
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = ""  # where the job was found

    def transition(self, new_status: ApplicationStatus, note: str = "") -> bool:
        """Attempt to transition to a new status. Returns True if valid."""
        valid_next = VALID_TRANSITIONS.get(self.status, [])
        if new_status not in valid_next:
            return False

        event = StatusEvent(
            from_status=self.status,
            to_status=new_status,
            timestamp=datetime.now(timezone.utc).isoformat(),
            note=note,
        )
        self.history.append(event)
        self.status = new_status
        self.last_updated = event.timestamp

        if new_status == ApplicationStatus.APPLIED and not self.applied_date:
            self.applied_date = event.timestamp

        return True

    def is_active(self) -> bool:
        """Check if application is still in an active state."""
        return self.status in ApplicationStatus.active_states()

    def days_since_applied(self) -> Optional[int]:
        """Days since application was submitted."""
        if not self.applied_date:
            return None
        applied = datetime.fromisoformat(self.applied_date)
        now = datetime.now(timezone.utc)
        return (now - applied).days

    def days_in_current_status(self) -> int:
        """Days spent in current status."""
        if not self.history:
            return 0
        last_change = datetime.fromisoformat(self.history[-1].timestamp)
        now = datetime.now(timezone.utc)
        return (now - last_change).days

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "status": self.status.value,
            "applied_date": self.applied_date,
            "last_updated": self.last_updated,
            "is_active": self.is_active(),
            "days_since_applied": self.days_since_applied(),
            "days_in_current_status": self.days_in_current_status(),
            "history_count": len(self.history),
            "notes": self.notes,
            "tags": self.tags,
            "source": self.source,
        }


class ApplicationTracker:
    """Manages multiple job applications with filtering and stats."""

    def __init__(self):
        self.applications: Dict[str, Application] = {}

    def add(self, app: Application) -> None:
        self.applications[app.id] = app

    def get(self, app_id: str) -> Optional[Application]:
        return self.applications.get(app_id)

    def get_by_status(self, status: ApplicationStatus) -> List[Application]:
        return [a for a in self.applications.values() if a.status == status]

    def get_active(self) -> List[Application]:
        return [a for a in self.applications.values() if a.is_active()]

    def stats(self) -> dict:
        """Aggregate statistics across all applications."""
        apps = list(self.applications.values())
        total = len(apps)
        if total == 0:
            return {"total": 0}

        status_counts = {}
        for a in apps:
            s = a.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        active = sum(1 for a in apps if a.is_active())
        offers = status_counts.get(ApplicationStatus.ACCEPTED.value, 0)
        response_rate = 0
        applied = sum(1 for a in apps if a.status != ApplicationStatus.SAVED)
        if applied > 0:
            responded = sum(1 for a in apps if a.status not in (
                ApplicationStatus.SAVED, ApplicationStatus.APPLIED, ApplicationStatus.WITHDRAWN
            ))
            response_rate = round(responded / applied * 100, 1)

        return {
            "total": total,
            "active": active,
            "by_status": status_counts,
            "offers_accepted": offers,
            "response_rate_pct": response_rate,
        }

    def export_json(self) -> str:
        return json.dumps(
            {"applications": [a.to_dict() for a in self.applications.values()], "stats": self.stats()},
            indent=2, ensure_ascii=False
        )


__all__ = ["ApplicationStatus", "Application", "ApplicationTracker", "StatusEvent", "VALID_TRANSITIONS"]
