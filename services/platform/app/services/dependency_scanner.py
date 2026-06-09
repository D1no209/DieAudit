from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx


class DependencyScanner:
    def __init__(self, workspace_path: str) -> None:
        self.workspace = Path(workspace_path).resolve()

    async def scan_osv(self) -> dict[str, Any]:
        packages = self.detect_dependencies()
        queries = [
            {"package": {"name": package["name"], "ecosystem": package["ecosystem"]}, "version": package["version"]}
            for package in packages
            if package.get("version")
        ]
        if not queries:
            return {"packages": packages, "vulnerabilities": [], "findings": []}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.osv.dev/v1/querybatch", json={"queries": queries})
            response.raise_for_status()
        results = response.json().get("results", [])
        vulnerabilities = []
        findings = []
        for package, result in zip(packages, results, strict=False):
            for vuln in result.get("vulns", []) or []:
                normalized = {
                    "package": package,
                    "id": vuln.get("id"),
                    "aliases": vuln.get("aliases", []),
                    "summary": vuln.get("summary"),
                    "details": vuln.get("details"),
                    "modified": vuln.get("modified"),
                    "published": vuln.get("published"),
                    "database_specific": vuln.get("database_specific", {}),
                }
                vulnerabilities.append(normalized)
                findings.append(
                    {
                        "title": f"Vulnerable dependency {package['name']} {package.get('version')}",
                        "severity": self._severity(vuln),
                        "status": "candidate",
                        "file_path": package.get("manifest"),
                        "line_start": None,
                        "line_end": None,
                        "rule_id": vuln.get("id"),
                        "description": vuln.get("summary") or vuln.get("details"),
                        "source": "sca-osv",
                        "raw": normalized,
                    }
                )
        return {"packages": packages, "vulnerabilities": vulnerabilities, "findings": findings}

    def detect_dependencies(self) -> list[dict[str, Any]]:
        packages = [*self._npm_package_lock(), *self._python_requirements()]
        seen = set()
        deduped = []
        for item in packages:
            key = (item["ecosystem"], item["name"].lower(), item.get("version"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _npm_package_lock(self) -> list[dict[str, Any]]:
        result = []
        for lockfile in self.workspace.rglob("package-lock.json"):
            if not self._is_safe_file(lockfile):
                continue
            data = json.loads(lockfile.read_text(encoding="utf-8", errors="replace"))
            for path, body in (data.get("packages") or {}).items():
                if not path.startswith("node_modules/"):
                    continue
                name = body.get("name") or path.removeprefix("node_modules/")
                version = body.get("version")
                if name and version:
                    result.append(
                        {
                            "ecosystem": "npm",
                            "name": name,
                            "version": version,
                            "manifest": lockfile.relative_to(self.workspace).as_posix(),
                        }
                    )
        return result

    def _python_requirements(self) -> list[dict[str, Any]]:
        result = []
        pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.!+-]+)")
        for requirements in self.workspace.rglob("requirements*.txt"):
            if not self._is_safe_file(requirements):
                continue
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
                match = pattern.match(line)
                if match:
                    result.append(
                        {
                            "ecosystem": "PyPI",
                            "name": match.group(1),
                            "version": match.group(2),
                            "manifest": requirements.relative_to(self.workspace).as_posix(),
                        }
                    )
        return result

    def _is_safe_file(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return resolved.is_file() and (resolved == self.workspace or self.workspace in resolved.parents)

    @staticmethod
    def _severity(vuln: dict[str, Any]) -> str:
        severities = vuln.get("severity") or []
        for item in severities:
            score = item.get("score", "")
            if score.startswith("CVSS:") and any(token in score for token in ("/C:H", "/C:C")):
                return "high"
        aliases = " ".join(vuln.get("aliases", []))
        if "GHSA" in aliases or "CVE" in aliases:
            return "medium"
        return "unknown"
