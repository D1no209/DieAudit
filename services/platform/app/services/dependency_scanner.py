from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
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
        packages = [
            *self._npm_package_lock(),
            *self._yarn_lock(),
            *self._pnpm_lock(),
            *self._python_requirements(),
            *self._python_pyproject(),
            *self._python_poetry_lock(),
            *self._go_mod(),
            *self._cargo_lock(),
            *self._composer_lock(),
            *self._maven_pom(),
        ]
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
            try:
                data = json.loads(lockfile.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            manifest = lockfile.relative_to(self.workspace).as_posix()
            for path, body in (data.get("packages") or {}).items():
                if path.startswith("node_modules/") and isinstance(body, dict):
                    name = body.get("name") or path.removeprefix("node_modules/")
                    version = body.get("version")
                    if name and version:
                        result.append(self._package("npm", name, version, manifest))
            self._collect_npm_dependencies(data.get("dependencies") or {}, manifest, result)
        return result

    def _collect_npm_dependencies(self, dependencies: dict[str, Any], manifest: str, result: list[dict[str, Any]]) -> None:
        for name, body in dependencies.items():
            if not isinstance(body, dict):
                continue
            version = body.get("version")
            if name and version:
                result.append(self._package("npm", name, version, manifest))
            nested = body.get("dependencies")
            if isinstance(nested, dict):
                self._collect_npm_dependencies(nested, manifest, result)

    def _yarn_lock(self) -> list[dict[str, Any]]:
        result = []
        for lockfile in self.workspace.rglob("yarn.lock"):
            if not self._is_safe_file(lockfile):
                continue
            manifest = lockfile.relative_to(self.workspace).as_posix()
            current_name: str | None = None
            current_version: str | None = None
            for raw_line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.rstrip()
                if line and not line.startswith((" ", "\t")) and line.endswith(":"):
                    if current_name and current_version:
                        result.append(self._package("npm", current_name, current_version, manifest))
                    current_name = self._npm_name_from_descriptor(line[:-1].split(",", 1)[0].strip().strip('"'))
                    current_version = None
                elif current_name:
                    match = re.match(r'^\s+version\s+"?([^"\s]+)"?', line)
                    if match:
                        current_version = match.group(1)
            if current_name and current_version:
                result.append(self._package("npm", current_name, current_version, manifest))
        return result

    def _pnpm_lock(self) -> list[dict[str, Any]]:
        result = []
        pattern = re.compile(r"^\s{2,}/?((?:@[^/\s]+/)?[^@\s/]+)@([^:\s(]+)")
        for lockfile in self.workspace.rglob("pnpm-lock.yaml"):
            if not self._is_safe_file(lockfile):
                continue
            manifest = lockfile.relative_to(self.workspace).as_posix()
            for line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
                match = pattern.match(line)
                if match:
                    result.append(self._package("npm", match.group(1), match.group(2), manifest))
        return result

    def _python_requirements(self) -> list[dict[str, Any]]:
        result = []
        pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*={2,3}\s*([A-Za-z0-9_.!+-]+)")
        for requirements in self.workspace.rglob("requirements*.txt"):
            if not self._is_safe_file(requirements):
                continue
            manifest = requirements.relative_to(self.workspace).as_posix()
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
                match = pattern.match(line)
                if match:
                    result.append(self._package("PyPI", match.group(1), match.group(2), manifest))
        return result

    def _python_pyproject(self) -> list[dict[str, Any]]:
        result = []
        for pyproject in self.workspace.rglob("pyproject.toml"):
            if not self._is_safe_file(pyproject):
                continue
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
            except tomllib.TOMLDecodeError:
                continue
            manifest = pyproject.relative_to(self.workspace).as_posix()
            for spec in (data.get("project") or {}).get("dependencies") or []:
                parsed = self._python_exact_requirement(str(spec))
                if parsed:
                    result.append(self._package("PyPI", parsed[0], parsed[1], manifest))
            poetry_dependencies = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            for name, spec in poetry_dependencies.items():
                if str(name).lower() == "python":
                    continue
                version = self._poetry_dependency_version(spec)
                if version:
                    result.append(self._package("PyPI", name, version, manifest))
        return result

    def _python_poetry_lock(self) -> list[dict[str, Any]]:
        result = []
        for lockfile in self.workspace.rglob("poetry.lock"):
            if not self._is_safe_file(lockfile):
                continue
            manifest = lockfile.relative_to(self.workspace).as_posix()
            name = None
            version = None
            for line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip() == "[[package]]":
                    if name and version:
                        result.append(self._package("PyPI", name, version, manifest))
                    name = None
                    version = None
                elif line.startswith("name = "):
                    name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("version = "):
                    version = line.split("=", 1)[1].strip().strip('"')
            if name and version:
                result.append(self._package("PyPI", name, version, manifest))
        return result

    def _go_mod(self) -> list[dict[str, Any]]:
        result = []
        pattern = re.compile(r"^\s*([A-Za-z0-9_.~/-]+)\s+(v[^\s]+)")
        for gomod in self.workspace.rglob("go.mod"):
            if not self._is_safe_file(gomod):
                continue
            manifest = gomod.relative_to(self.workspace).as_posix()
            for line in gomod.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith(("//", "module ", "go ", "require (", ")")):
                    continue
                if stripped.startswith("require "):
                    stripped = stripped.removeprefix("require ").strip()
                match = pattern.match(stripped)
                if match:
                    result.append(self._package("Go", match.group(1), match.group(2), manifest))
        return result

    def _cargo_lock(self) -> list[dict[str, Any]]:
        result = []
        for lockfile in self.workspace.rglob("Cargo.lock"):
            if not self._is_safe_file(lockfile):
                continue
            manifest = lockfile.relative_to(self.workspace).as_posix()
            name = None
            version = None
            for line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip() == "[[package]]":
                    if name and version:
                        result.append(self._package("crates.io", name, version, manifest))
                    name = None
                    version = None
                elif line.startswith("name = "):
                    name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("version = "):
                    version = line.split("=", 1)[1].strip().strip('"')
            if name and version:
                result.append(self._package("crates.io", name, version, manifest))
        return result

    def _composer_lock(self) -> list[dict[str, Any]]:
        result = []
        for lockfile in self.workspace.rglob("composer.lock"):
            if not self._is_safe_file(lockfile):
                continue
            try:
                data = json.loads(lockfile.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            manifest = lockfile.relative_to(self.workspace).as_posix()
            for body in [*(data.get("packages") or []), *(data.get("packages-dev") or [])]:
                name = body.get("name") if isinstance(body, dict) else None
                version = body.get("version") if isinstance(body, dict) else None
                if name and version:
                    result.append(self._package("Packagist", name, str(version).lstrip("v"), manifest))
        return result

    def _maven_pom(self) -> list[dict[str, Any]]:
        result = []
        for pom in self.workspace.rglob("pom.xml"):
            if not self._is_safe_file(pom):
                continue
            try:
                root = ET.fromstring(pom.read_text(encoding="utf-8", errors="replace"))
            except ET.ParseError:
                continue
            manifest = pom.relative_to(self.workspace).as_posix()
            properties = self._maven_properties(root)
            for dep in root.findall(".//{*}dependencies/{*}dependency"):
                group_id = self._xml_child_text(dep, "groupId")
                artifact_id = self._xml_child_text(dep, "artifactId")
                version = self._resolve_maven_property(self._xml_child_text(dep, "version"), properties)
                if group_id and artifact_id and version:
                    result.append(self._package("Maven", f"{group_id}:{artifact_id}", version, manifest))
        return result

    @staticmethod
    def _package(ecosystem: str, name: str, version: str, manifest: str) -> dict[str, Any]:
        return {
            "ecosystem": ecosystem,
            "name": str(name).strip(),
            "version": str(version).strip(),
            "manifest": manifest,
        }

    @staticmethod
    def _npm_name_from_descriptor(descriptor: str) -> str | None:
        descriptor = descriptor.strip().strip("'\"")
        if descriptor.startswith("@"):
            index = descriptor.rfind("@")
            return descriptor[:index] if index > 0 else None
        return descriptor.rsplit("@", 1)[0] if "@" in descriptor else descriptor or None

    @staticmethod
    def _python_exact_requirement(spec: str) -> tuple[str, str] | None:
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*={2,3}\s*([A-Za-z0-9_.!+-]+)", spec)
        return (match.group(1), match.group(2)) if match else None

    @classmethod
    def _poetry_dependency_version(cls, spec: Any) -> str | None:
        if isinstance(spec, str):
            if spec and not any(spec.startswith(prefix) for prefix in ("^", "~", ">", "<", "*")):
                return spec.strip("=")
            parsed = cls._python_exact_requirement(f"pkg{spec}" if spec.startswith("==") else f"pkg=={spec}")
            return parsed[1] if parsed and spec.startswith("==") else None
        if isinstance(spec, dict):
            return cls._poetry_dependency_version(spec.get("version"))
        return None

    @staticmethod
    def _maven_properties(root: ET.Element) -> dict[str, str]:
        properties: dict[str, str] = {}
        for item in root.findall(".//{*}properties/*"):
            tag = item.tag.rsplit("}", 1)[-1]
            if item.text:
                properties[tag] = item.text.strip()
        return properties

    @staticmethod
    def _xml_child_text(element: ET.Element, name: str) -> str | None:
        child = element.find(f"{{*}}{name}")
        return child.text.strip() if child is not None and child.text else None

    @staticmethod
    def _resolve_maven_property(value: str | None, properties: dict[str, str]) -> str | None:
        if not value:
            return None
        match = re.fullmatch(r"\$\{([^}]+)}", value.strip())
        return properties.get(match.group(1)) if match else value.strip()

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
