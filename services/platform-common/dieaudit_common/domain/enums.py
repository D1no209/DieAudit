from enum import StrEnum


class AuditRunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    WARNING = "warning"


class FailurePolicy(StrEnum):
    FAIL_FAST = "fail_fast"
    CONTINUE_WITH_WARNING = "continue_with_warning"
    ALWAYS_RUN = "always_run"
