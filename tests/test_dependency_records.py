from __future__ import annotations

import pytest

from app.api.routes import _dependency_key, _dependency_vulnerability_map, _replace_dependency_records
from app.domain.models import DependencyRecord


class FakeSession:
    def __init__(self) -> None:
        self.executed: list[object] = []
        self.added: list[DependencyRecord] = []

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    def add(self, row: DependencyRecord) -> None:
        self.added.append(row)


def test_dependency_vulnerability_map_matches_ecosystem_name_and_version() -> None:
    vulnerability = {
        "id": "GHSA-demo",
        "package": {"ecosystem": "npm", "name": "express", "version": "4.18.2"},
    }

    mapped = _dependency_vulnerability_map([vulnerability])

    assert mapped[_dependency_key({"ecosystem": "npm", "name": "express", "version": "4.18.2"})] == [vulnerability]
    assert _dependency_key({"ecosystem": "npm", "name": "express", "version": "4.18.3"}) not in mapped


@pytest.mark.asyncio
async def test_replace_dependency_records_dedupes_and_attaches_vulnerabilities() -> None:
    session = FakeSession()

    created = await _replace_dependency_records(
        session=session,
        audit_run_id="run-1",
        project_id="project-1",
        packages=[
            {"ecosystem": "npm", "name": "express", "version": "4.18.2", "manifest": "package-lock.json"},
            {"ecosystem": "npm", "name": "Express", "version": "4.18.2", "manifest": "package-lock.json"},
            {"ecosystem": "PyPI", "name": "django", "version": "4.2.10", "manifest": "requirements.txt"},
            {"ecosystem": "npm", "name": "", "version": "1.0.0", "manifest": "package-lock.json"},
            "not-a-package",
        ],
        vulnerabilities=[
            {
                "id": "GHSA-demo",
                "package": {"ecosystem": "npm", "name": "express", "version": "4.18.2"},
            }
        ],
    )

    assert created == 2
    assert len(session.executed) == 1
    assert [(row.ecosystem, row.name, row.version, row.manifest) for row in session.added] == [
        ("npm", "express", "4.18.2", "package-lock.json"),
        ("PyPI", "django", "4.2.10", "requirements.txt"),
    ]
    assert session.added[0].vulnerability_count == 1
    assert session.added[0].vulnerabilities[0]["id"] == "GHSA-demo"
    assert session.added[1].vulnerability_count == 0
