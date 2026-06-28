from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


AUDIT_RUN_STARTED = "dieaudit.audit_run.started"
AUDIT_RUN_STAGE_STARTED = "dieaudit.audit_run.stage.started"
AUDIT_RUN_STAGE_COMPLETED = "dieaudit.audit_run.stage.completed"
AUDIT_RUN_STAGE_FAILED = "dieaudit.audit_run.stage.failed"
AUDIT_RUN_CANCELLED = "dieaudit.audit_run.cancelled"
AGENT_RUN_COMPLETED = "dieaudit.agent_run.completed"
FINDING_UPDATED = "dieaudit.finding.updated"


@dataclass(frozen=True)
class DomainEvent:
    subject: str
    event_type: str
    audit_run_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "subject": self.subject,
            "event_type": self.event_type,
            "audit_run_id": self.audit_run_id,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
        }
