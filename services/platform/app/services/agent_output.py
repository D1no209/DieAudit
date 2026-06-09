from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from app.domain.models import AgentRunEvent, Evidence, Finding
from app.repositories import SessionLocal


REQUIRED_FINDING_FIELDS = {"title", "severity", "file_path", "line_start", "description", "confidence", "source"}


class AgentOutputIngestor:
    async def ingest(
        self,
        *,
        agent_run_id: str,
        audit_run_id: str,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        structured, warnings = self._extract_structured_payload(payload)
        findings_payload = structured.get("findings", []) if isinstance(structured, dict) else []
        evidence_payload = structured.get("evidence", []) if isinstance(structured, dict) else []
        summary = structured.get("summary") if isinstance(structured, dict) else None

        created_findings: list[Finding] = []
        created_evidence: list[Evidence] = []

        async with SessionLocal() as session:
            for index, item in enumerate(findings_payload if isinstance(findings_payload, list) else []):
                if not isinstance(item, dict):
                    warnings.append({"kind": "finding_invalid_type", "index": index})
                    continue
                missing = sorted(field for field in REQUIRED_FINDING_FIELDS if field not in item)
                if missing:
                    warnings.append({"kind": "finding_missing_fields", "index": index, "missing": missing})
                    continue
                if not item.get("title") or not item.get("file_path") or not item.get("description") or not item.get("source"):
                    warnings.append({"kind": "finding_empty_required_value", "index": index})
                    continue

                finding = Finding(
                    finding_id=str(uuid.uuid4()),
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    title=str(item["title"])[:255],
                    severity=str(item.get("severity") or "unknown").lower(),
                    status=str(item.get("status") or "candidate"),
                    file_path=str(item["file_path"]),
                    line_start=self._optional_int(item.get("line_start")),
                    line_end=self._optional_int(item.get("line_end")),
                    rule_id=str(item["rule_id"]) if item.get("rule_id") else None,
                    description=str(item["description"]),
                    source=str(item["source"]),
                    raw={**item, "agent_run_id": agent_run_id},
                )
                session.add(finding)
                created_findings.append(finding)

                for evidence_item in self._finding_evidence_items(item):
                    evidence = self._evidence_from_payload(
                        evidence_item,
                        finding_id=finding.finding_id,
                        audit_run_id=audit_run_id,
                        default_kind="agent-finding",
                    )
                    session.add(evidence)
                    created_evidence.append(evidence)

            for index, item in enumerate(evidence_payload if isinstance(evidence_payload, list) else []):
                if not isinstance(item, dict):
                    warnings.append({"kind": "evidence_invalid_type", "index": index})
                    continue
                finding = self._resolve_evidence_finding(item, created_findings)
                if finding is None:
                    warnings.append({"kind": "evidence_unmatched_finding", "index": index})
                    continue
                evidence = self._evidence_from_payload(
                    item,
                    finding_id=finding.finding_id,
                    audit_run_id=audit_run_id,
                    default_kind="agent-output",
                )
                session.add(evidence)
                created_evidence.append(evidence)

            if warnings:
                session.add(
                    AgentRunEvent(
                        agent_run_id=agent_run_id,
                        event_type="structured_output_parse_warnings",
                        payload={"warnings": warnings},
                    )
                )
            if structured:
                session.add(
                    AgentRunEvent(
                        agent_run_id=agent_run_id,
                        event_type="structured_output_ingested",
                        payload={
                            "summary": summary,
                            "findings_created": len(created_findings),
                            "evidence_created": len(created_evidence),
                        },
                    )
                )
            await session.commit()

        return {
            "summary": summary,
            "findings_created": len(created_findings),
            "evidence_created": len(created_evidence),
            "warnings": warnings,
        }

    def _extract_structured_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        warnings: list[dict[str, Any]] = []
        for candidate in self._walk(payload):
            if isinstance(candidate, dict) and ("findings" in candidate or "evidence" in candidate):
                return candidate, warnings
            if isinstance(candidate, str) and ("findings" in candidate or "evidence" in candidate):
                parsed = self._parse_json_from_text(candidate)
                if parsed is not None:
                    return parsed, warnings
        warnings.append({"kind": "structured_output_not_found"})
        return {}, warnings

    def _walk(self, value: Any) -> Iterable[Any]:
        yield value
        if isinstance(value, dict):
            for item in value.values():
                yield from self._walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from self._walk(item)

    @staticmethod
    def _parse_json_from_text(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        candidates = [stripped]
        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
        candidates.extend(fenced)
        first = stripped.find("{")
        last = stripped.rfind("}")
        if first >= 0 and last > first:
            candidates.append(stripped[first : last + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _finding_evidence_items(item: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = item.get("evidence")
        if isinstance(evidence, list):
            return [entry for entry in evidence if isinstance(entry, dict)]
        if isinstance(evidence, dict):
            return [evidence]
        return [
            {
                "kind": "agent-finding",
                "summary": item.get("description"),
                "payload": {"confidence": item.get("confidence"), "file_path": item.get("file_path")},
            }
        ]

    @staticmethod
    def _resolve_evidence_finding(item: dict[str, Any], findings: list[Finding]) -> Finding | None:
        finding_index = item.get("finding_index")
        if isinstance(finding_index, int) and 0 <= finding_index < len(findings):
            return findings[finding_index]
        finding_id = item.get("finding_id")
        for finding in findings:
            if finding.finding_id == finding_id:
                return finding
        title = item.get("finding_title")
        for finding in findings:
            if title and finding.title == title:
                return finding
        return findings[0] if len(findings) == 1 else None

    @staticmethod
    def _evidence_from_payload(
        item: dict[str, Any],
        *,
        finding_id: str,
        audit_run_id: str,
        default_kind: str,
    ) -> Evidence:
        return Evidence(
            evidence_id=str(uuid.uuid4()),
            finding_id=finding_id,
            audit_run_id=audit_run_id,
            kind=str(item.get("kind") or default_kind),
            summary=str(item["summary"]) if item.get("summary") else None,
            artifact_path=str(item["artifact_path"]) if item.get("artifact_path") else None,
            payload=item.get("payload") if isinstance(item.get("payload"), dict) else item,
        )


async def get_findings_for_audit_run(audit_run_id: str) -> list[Finding]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.asc()))
        ).scalars()
        return list(rows)
