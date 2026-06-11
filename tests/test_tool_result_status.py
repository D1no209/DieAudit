from __future__ import annotations

from app.api.routes import _sca_status, _semgrep_status


def test_semgrep_status_distinguishes_unavailable_failed_and_results() -> None:
    assert _semgrep_status({"available": False, "error": "missing"}) == {
        "ok": False,
        "status": "unavailable",
        "reason": "missing",
    }
    assert _semgrep_status({"ok": False, "available": True, "stderr": "bad config"}) == {
        "ok": False,
        "status": "failed",
        "reason": "bad config",
    }
    assert _semgrep_status({"ok": True, "available": True, "findings": []}) == {
        "ok": True,
        "status": "no_findings",
        "reason": None,
    }
    assert _semgrep_status({"ok": True, "available": True, "findings": [{"title": "x"}]}) == {
        "ok": True,
        "status": "has_findings",
        "reason": None,
    }


def test_sca_status_distinguishes_syft_osv_and_manifest_coverage() -> None:
    assert _sca_status({"available": False, "error": "missing syft"}, {}, []) == {
        "ok": False,
        "status": "syft_unavailable",
        "reason": "missing syft",
    }
    assert _sca_status({"ok": True}, {"ok": False, "error": "timeout"}, [{"name": "express"}]) == {
        "ok": False,
        "status": "osv_unreachable",
        "reason": "timeout",
    }
    assert _sca_status({"ok": True}, {"ok": True, "available": True}, []) == {
        "ok": True,
        "status": "no_dependencies",
        "reason": "no supported dependency manifests with pinned versions were detected",
    }
    assert _sca_status({"ok": True}, {"ok": True, "available": True}, [{"name": "express"}]) == {
        "ok": True,
        "status": "completed",
        "reason": None,
    }
