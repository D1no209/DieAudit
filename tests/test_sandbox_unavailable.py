from __future__ import annotations

from app.api.routes import _is_sandbox_unavailable_error, _sandbox_unavailable_result


def test_sandbox_unavailable_detection_matches_isolation_policy_errors() -> None:
    assert _is_sandbox_unavailable_error("Sandbox execution requires gVisor/Kata or explicit ALLOW_RUNC_SANDBOX=true")
    assert _is_sandbox_unavailable_error("gVisor is enabled but Docker runtime 'runsc' is not installed.")
    assert not _is_sandbox_unavailable_error("sandbox network belongs to a different audit run")


def test_sandbox_unavailable_result_is_explicit() -> None:
    result = _sandbox_unavailable_result("runsc missing", request_body={"image": "python"})

    assert result == {
        "ok": False,
        "status": "unavailable",
        "reason": "runsc missing",
        "request": {"image": "python"},
    }
