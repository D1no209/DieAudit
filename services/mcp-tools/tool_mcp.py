import os
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse


MCP_NAME = os.environ.get("MCP_NAME", "dieaudit-tool-mcp")
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()
MAX_READ_BYTES = int(os.environ.get("MAX_READ_BYTES", "200000"))
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "100"))
ARTIFACT_ROOT = Path(os.environ.get("ARTIFACT_ROOT", "/artifacts")).resolve()

mcp = FastMCP(MCP_NAME, host="0.0.0.0", port=8001, stateless_http=True)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"ok": True, "service": MCP_NAME, "workspace_root": str(WORKSPACE_ROOT)})


@mcp.custom_route("/tools/semgrep_scan", methods=["POST"])
async def semgrep_scan_route(request):
    body = await request.json()
    return JSONResponse(
        semgrep_scan(
            config=body.get("config", "auto"),
            output_format=body.get("output_format", "json"),
            timeout_seconds=int(body.get("timeout_seconds", 120)),
        )
    )


@mcp.custom_route("/tools/detect_dependencies", methods=["POST"])
async def detect_dependencies_route(request):
    return JSONResponse(detect_dependencies())


@mcp.custom_route("/tools/generate_sbom", methods=["POST"])
async def generate_sbom_route(request):
    body = await request.json()
    return JSONResponse(
        generate_sbom(
            output_format=body.get("output_format", "spdx-json"),
            timeout_seconds=int(body.get("timeout_seconds", 120)),
        )
    )


@mcp.custom_route("/tools/query_osv", methods=["POST"])
async def query_osv_route(request):
    body = await request.json()
    return JSONResponse(query_osv(max_packages=int(body.get("max_packages", 200))))


@mcp.tool()
def list_files(path: str = ".", max_results: int = 200) -> dict[str, Any]:
    """List files under the authorized workspace."""
    root = _safe_path(path)
    max_results = min(max(max_results, 1), 1000)
    entries: list[dict[str, Any]] = []
    for item in sorted(root.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
        rel = item.relative_to(WORKSPACE_ROOT).as_posix()
        entries.append({"path": rel, "type": "directory" if item.is_dir() else "file", "size": item.stat().st_size})
        if len(entries) >= max_results:
            break
    return {"root": root.relative_to(WORKSPACE_ROOT).as_posix() if root != WORKSPACE_ROOT else ".", "entries": entries}


@mcp.tool()
def read_file(path: str, offset: int = 0, limit: int = 20000) -> dict[str, Any]:
    """Read a UTF-8 text file under the authorized workspace."""
    target = _safe_path(path)
    if not target.is_file():
        raise ValueError(f"not a file: {path}")
    data = target.read_bytes()[:MAX_READ_BYTES]
    text = data.decode("utf-8", errors="replace")
    offset = max(offset, 0)
    limit = min(max(limit, 1), MAX_READ_BYTES)
    return {
        "path": target.relative_to(WORKSPACE_ROOT).as_posix(),
        "offset": offset,
        "limit": limit,
        "truncated": target.stat().st_size > MAX_READ_BYTES,
        "content": text[offset : offset + limit],
    }


@mcp.tool()
def search_code(pattern: str, path: str = ".", max_results: int = 100) -> dict[str, Any]:
    """Search workspace text using ripgrep."""
    root = _safe_path(path)
    max_results = min(max(max_results, 1), MAX_SEARCH_RESULTS)
    command = [
        "rg",
        "--line-number",
        "--column",
        "--no-heading",
        "--color",
        "never",
        "--max-count",
        str(max_results),
        pattern,
        str(root),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode not in {0, 1}:
        raise RuntimeError((result.stderr or "ripgrep failed").strip())
    matches = []
    for line in result.stdout.splitlines()[:max_results]:
        file_name, line_no, column, text = _split_rg_line(line)
        matches.append(
            {
                "path": _safe_path(file_name).relative_to(WORKSPACE_ROOT).as_posix(),
                "line": int(line_no),
                "column": int(column),
                "text": text,
            }
        )
    return {"pattern": pattern, "matches": matches}


@mcp.tool()
def read_snippet(path: str, line: int, context: int = 5) -> dict[str, Any]:
    """Read a line-oriented snippet around a source location."""
    target = _safe_path(path)
    if not target.is_file():
        raise ValueError(f"not a file: {path}")
    context = min(max(context, 0), 50)
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(line - context, 1)
    end = min(line + context, len(lines))
    snippet = [
        {"line": index, "text": lines[index - 1]}
        for index in range(start, end + 1)
    ]
    return {"path": target.relative_to(WORKSPACE_ROOT).as_posix(), "start": start, "end": end, "snippet": snippet}


@mcp.tool()
def semgrep_scan(
    config: str = "auto",
    output_format: str = "json",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Run Semgrep against the authorized workspace and persist the raw result as an artifact."""
    semgrep = shutil.which("semgrep")
    if not semgrep:
        return {
            "ok": False,
            "available": False,
            "error": "semgrep executable is not installed in this MCP image",
            "findings": [],
        }
    if output_format not in {"json", "sarif"}:
        raise ValueError("output_format must be json or sarif")
    timeout_seconds = min(max(timeout_seconds, 5), 900)
    artifact_dir = _artifact_dir("semgrep")
    output_path = artifact_dir / f"semgrep-results.{output_format}"
    command = [
        semgrep,
        "scan",
        "--config",
        config,
        f"--{output_format}",
        "--output",
        str(output_path),
        str(WORKSPACE_ROOT),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "available": True,
            "timeout_seconds": timeout_seconds,
            "error": "semgrep scan timed out",
            "stdout": _tail_text(exc.stdout),
            "stderr": _tail_text(exc.stderr),
            "artifact_path": str(output_path) if output_path.exists() else None,
            "findings": [],
        }
    if result.returncode not in {0, 1}:
        return {
            "ok": False,
            "available": True,
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "artifact_path": str(output_path) if output_path.exists() else None,
            "findings": [],
        }
    parsed = _load_json_artifact(output_path) if output_format == "json" else None
    findings = _semgrep_findings(parsed) if parsed else []
    return {
        "ok": True,
        "available": True,
        "exit_code": result.returncode,
        "artifact_path": str(output_path),
        "findings": findings,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


@mcp.tool()
def semgrep_results(artifact_path: str) -> dict[str, Any]:
    """Read a previously generated Semgrep JSON artifact."""
    target = _safe_artifact_path(artifact_path)
    data = _load_json_artifact(target)
    return {"artifact_path": str(target), "findings": _semgrep_findings(data), "raw": data}


@mcp.tool()
def detect_dependencies() -> dict[str, Any]:
    """Detect dependencies from common project manifest and lock files."""
    packages = _detect_dependencies()
    return {"packages": packages, "count": len(packages)}


@mcp.tool()
def generate_sbom(output_format: str = "spdx-json", timeout_seconds: int = 120) -> dict[str, Any]:
    """Generate an SBOM with Syft when the executable is available."""
    syft = shutil.which("syft")
    if not syft:
        return {
            "ok": False,
            "available": False,
            "error": "syft executable is not installed in this MCP image",
            "artifact_path": None,
        }
    timeout_seconds = min(max(timeout_seconds, 5), 900)
    safe_format = re.sub(r"[^A-Za-z0-9_.-]+", "-", output_format)
    artifact_dir = _artifact_dir("sbom")
    output_path = artifact_dir / f"sbom.{safe_format}.json"
    command = [syft, str(WORKSPACE_ROOT), "-o", output_format]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "available": True,
            "timeout_seconds": timeout_seconds,
            "error": "syft sbom generation timed out",
            "stdout": _tail_text(exc.stdout),
            "stderr": _tail_text(exc.stderr),
            "artifact_path": None,
        }
    if result.returncode != 0:
        return {
            "ok": False,
            "available": True,
            "exit_code": result.returncode,
            "stderr": result.stderr[-4000:],
            "artifact_path": None,
        }
    output_path.write_text(result.stdout, encoding="utf-8")
    return {
        "ok": True,
        "available": True,
        "exit_code": result.returncode,
        "artifact_path": str(output_path),
        "bytes": output_path.stat().st_size,
    }


@mcp.tool()
def query_osv(max_packages: int = 200) -> dict[str, Any]:
    """Query OSV for detected dependency vulnerabilities."""
    packages = _detect_dependencies()[: max(1, min(max_packages, 1000))]
    queries = [{"package": {"name": item["name"], "ecosystem": item["ecosystem"]}, "version": item["version"]} for item in packages if item.get("version")]
    if not queries:
        return {"ok": True, "available": True, "packages": packages, "vulnerabilities": [], "findings": []}
    try:
        response = httpx.post("https://api.osv.dev/v1/querybatch", json={"queries": queries}, timeout=60)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "available": False,
            "error": f"osv query failed: {exc}",
            "packages": packages,
            "vulnerabilities": [],
            "findings": [],
        }
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
                    "severity": _osv_severity(vuln),
                    "status": "candidate",
                    "file_path": package.get("manifest"),
                    "line_start": None,
                    "line_end": None,
                    "rule_id": vuln.get("id"),
                    "description": vuln.get("summary") or vuln.get("details"),
                    "source": "sca-mcp",
                    "raw": normalized,
                }
            )
    return {"ok": True, "available": True, "packages": packages, "vulnerabilities": vulnerabilities, "findings": findings}


def _safe_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    resolved = candidate.resolve()
    if resolved != WORKSPACE_ROOT and WORKSPACE_ROOT not in resolved.parents:
        raise ValueError(f"path escapes workspace: {path}")
    return resolved


def _artifact_dir(kind: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", MCP_NAME).strip("-") or "tool-mcp"
    target = ARTIFACT_ROOT / safe_name / kind
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _safe_artifact_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ARTIFACT_ROOT / candidate
    resolved = candidate.resolve()
    if resolved != ARTIFACT_ROOT and ARTIFACT_ROOT not in resolved.parents:
        raise ValueError(f"path escapes artifact root: {path}")
    if not resolved.is_file():
        raise ValueError(f"artifact not found: {path}")
    return resolved


def _split_rg_line(line: str) -> tuple[str, str, str, str]:
    parts = line.split(":", 3)
    if len(parts) != 4:
        raise ValueError(f"unexpected ripgrep output: {line}")
    return parts[0], parts[1], parts[2], parts[3]


def _detect_dependencies() -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    packages.extend(_npm_package_lock())
    packages.extend(_python_requirements())
    seen = set()
    deduped = []
    for item in packages:
        key = (item["ecosystem"], item["name"].lower(), item.get("version"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _npm_package_lock() -> list[dict[str, Any]]:
    result = []
    for lockfile in WORKSPACE_ROOT.rglob("package-lock.json"):
        if not _is_safe_file(lockfile):
            continue
        data = json.loads(lockfile.read_text(encoding="utf-8", errors="replace"))
        packages = data.get("packages") or {}
        for path, body in packages.items():
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
                        "manifest": lockfile.relative_to(WORKSPACE_ROOT).as_posix(),
                    }
                )
    return result


def _python_requirements() -> list[dict[str, Any]]:
    result = []
    pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.!+-]+)")
    for requirements in WORKSPACE_ROOT.rglob("requirements*.txt"):
        if not _is_safe_file(requirements):
            continue
        for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line)
            if not match:
                continue
            result.append(
                {
                    "ecosystem": "PyPI",
                    "name": match.group(1),
                    "version": match.group(2),
                    "manifest": requirements.relative_to(WORKSPACE_ROOT).as_posix(),
                }
            )
    return result


def _is_safe_file(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return resolved.is_file() and (resolved == WORKSPACE_ROOT or WORKSPACE_ROOT in resolved.parents)


def _osv_severity(vuln: dict[str, Any]) -> str:
    severities = vuln.get("severity") or []
    for item in severities:
        score = item.get("score", "")
        if score.startswith("CVSS:"):
            if any(token in score for token in ("/C:H", "/C:C")):
                return "high"
    aliases = " ".join(vuln.get("aliases", []))
    if "GHSA" in aliases or "CVE" in aliases:
        return "medium"
    return "unknown"


def _load_json_artifact(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _tail_text(value: str | bytes | None, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]


def _semgrep_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for item in data.get("results", []) or []:
        extra = item.get("extra", {}) or {}
        path = item.get("path")
        start = item.get("start", {}) or {}
        end = item.get("end", {}) or {}
        check_id = item.get("check_id")
        findings.append(
            {
                "title": extra.get("message") or check_id or "Semgrep finding",
                "severity": str(extra.get("severity") or "unknown").lower(),
                "status": "candidate",
                "file_path": path,
                "line_start": start.get("line"),
                "line_end": end.get("line"),
                "rule_id": check_id,
                "description": extra.get("message"),
                "source": "semgrep-mcp",
                "raw": item,
            }
        )
    return findings


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
