import os
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse


MCP_NAME = os.environ.get("MCP_NAME", "dieaudit-tool-mcp")
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()
MAX_READ_BYTES = int(os.environ.get("MAX_READ_BYTES", "200000"))
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "100"))
ARTIFACT_ROOT = Path(os.environ.get("ARTIFACT_ROOT", "/artifacts")).resolve()
PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL") or os.environ.get("KNOWLEDGE_API_URL", "http://agent-gateway:8000")
PLATFORM_API_URL = PLATFORM_API_URL.rstrip("/")
API_KEY_HEADER = os.environ.get("API_KEY_HEADER", "X-DieAudit-Api-Key")
PLATFORM_API_KEY = os.environ.get("DIEAUDIT_API_KEY") or os.environ.get("KNOWLEDGE_API_KEY")
PROJECT_ID = os.environ.get("PROJECT_ID")
AUDIT_RUN_ID = os.environ.get("AUDIT_RUN_ID")
ENFORCE_PROJECT_FILTER = os.environ.get("ENFORCE_PROJECT_FILTER", "false").lower() in {"1", "true", "yes"}
HTTP_TEST_ALLOWED_HOSTS = {
    item.strip().lower()
    for item in os.environ.get("HTTP_TEST_ALLOWED_HOSTS", "").split(",")
    if item.strip()
}
HTTP_TEST_ALLOW_HOST_GATEWAY = os.environ.get("HTTP_TEST_ALLOW_HOST_GATEWAY", "false").lower() in {"1", "true", "yes"}
HTTP_TEST_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "docker-socket-proxy"}
if not HTTP_TEST_ALLOW_HOST_GATEWAY:
    HTTP_TEST_BLOCKED_HOSTS.update({"host.docker.internal", "host.containers.internal"})

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


@mcp.custom_route("/tools/search_knowledge", methods=["POST"])
async def search_knowledge_route(request):
    body = await request.json()
    return JSONResponse(
        await search_knowledge(
            query=body.get("query", ""),
            project_id=body.get("project_id"),
            include_global=bool(body.get("include_global", True)),
            limit=int(body.get("limit", 8)),
        )
    )


@mcp.custom_route("/tools/get_knowledge_document", methods=["POST"])
async def get_knowledge_document_route(request):
    body = await request.json()
    return JSONResponse(await get_knowledge_document(document_id=body.get("document_id", "")))


@mcp.custom_route("/tools/http_request", methods=["POST"])
async def http_request_route(request):
    body = await request.json()
    return JSONResponse(
        await http_request(
            method=body.get("method", "GET"),
            url=body.get("url", ""),
            headers=body.get("headers"),
            body=body.get("body"),
            json_body=body.get("json_body"),
            timeout_seconds=float(body.get("timeout_seconds", 15)),
            allow_redirects=bool(body.get("allow_redirects", False)),
        )
    )


@mcp.custom_route("/tools/run_poc", methods=["POST"])
async def run_poc_route(request):
    body = await request.json()
    return JSONResponse(await run_poc(**body))


@mcp.custom_route("/tools/start_sandbox_service", methods=["POST"])
async def start_sandbox_service_route(request):
    body = await request.json()
    return JSONResponse(await start_sandbox_service(**body))


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


@mcp.tool()
async def search_knowledge(
    query: str,
    project_id: str | None = None,
    include_global: bool = True,
    limit: int = 8,
) -> dict[str, Any]:
    """Search authorized global/project vulnerability knowledge."""
    if not query.strip():
        raise ValueError("query is required")
    scoped_project_id = _authorized_project_id(project_id)
    limit = min(max(limit, 1), 50)
    payload = {
        "query": query,
        "project_id": scoped_project_id,
        "include_global": include_global,
        "limit": limit,
    }
    return await _platform_post("/knowledge/search", payload)


@mcp.tool()
async def get_knowledge_document(document_id: str) -> dict[str, Any]:
    """Fetch an authorized knowledge document and its chunks."""
    if not document_id.strip():
        raise ValueError("document_id is required")
    document = await _platform_get(f"/knowledge/documents/{document_id}")
    _assert_document_authorized(document)
    chunks = await _platform_get(f"/knowledge/documents/{document_id}/chunks")
    return {"document": document, "chunks": chunks}


@mcp.tool()
async def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    json_body: dict[str, Any] | list[Any] | None = None,
    timeout_seconds: float = 15,
    allow_redirects: bool = False,
) -> dict[str, Any]:
    """Send a controlled HTTP request from the audit run network."""
    parsed = _validate_http_target(url)
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise ValueError("unsupported HTTP method")
    timeout_seconds = min(max(float(timeout_seconds), 1.0), 60.0)
    safe_headers = {str(key): str(value) for key, value in (headers or {}).items()}
    request_kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": safe_headers,
        "follow_redirects": allow_redirects,
    }
    if json_body is not None:
        request_kwargs["json"] = json_body
    elif body is not None:
        request_kwargs["content"] = body
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.request(**request_kwargs)
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "url": url,
            "method": method,
            "host": parsed.hostname,
            "error": str(exc),
        }
    return {
        "ok": True,
        "url": str(response.url),
        "method": method,
        "status_code": response.status_code,
        "reason_phrase": response.reason_phrase,
        "headers": _safe_response_headers(response.headers),
        "content_type": response.headers.get("content-type", ""),
        "body_truncated": len(response.content) > MAX_READ_BYTES,
        "body": response.text[:MAX_READ_BYTES],
    }


@mcp.tool()
async def run_poc(
    command: list[str],
    image: str = "python:3.12-slim",
    env: dict[str, str] | None = None,
    allow_external_network: bool = False,
    timeout_seconds: int = 120,
    expected_exit_code: int = 0,
    target_url: str | None = None,
    allow_weak_isolation: bool = False,
) -> dict[str, Any]:
    """Run a PoC command through the platform sandbox runner."""
    audit_run_id = _required_audit_run_id()
    if not command:
        raise ValueError("command is required")
    payload = {
        "image": image,
        "command": command,
        "env": env or {},
        "allow_external_network": allow_external_network,
        "timeout_seconds": timeout_seconds,
        "expected_exit_code": expected_exit_code,
        "target_url": target_url,
        "allow_weak_isolation": allow_weak_isolation,
    }
    return await _platform_post(f"/audit-runs/{audit_run_id}/sandbox/poc", payload)


@mcp.tool()
async def start_sandbox_service(
    image: str,
    command: list[str],
    service_name: str = "target",
    port: int = 8080,
    env: dict[str, str] | None = None,
    allow_external_network: bool = False,
    healthcheck_path: str | None = None,
    startup_timeout_seconds: int = 30,
    allow_weak_isolation: bool = False,
) -> dict[str, Any]:
    """Start a target service through the platform sandbox runner."""
    audit_run_id = _required_audit_run_id()
    if not command:
        raise ValueError("command is required")
    payload = {
        "image": image,
        "command": command,
        "env": env or {},
        "service_name": service_name,
        "port": port,
        "allow_external_network": allow_external_network,
        "healthcheck_path": healthcheck_path,
        "startup_timeout_seconds": startup_timeout_seconds,
        "allow_weak_isolation": allow_weak_isolation,
    }
    return await _platform_post(f"/audit-runs/{audit_run_id}/sandbox/service", payload)


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


def _authorized_project_id(project_id: str | None) -> str | None:
    requested = (project_id or PROJECT_ID or "").strip() or None
    if ENFORCE_PROJECT_FILTER and PROJECT_ID and requested and requested != PROJECT_ID:
        raise ValueError("project_id is not authorized for this MCP sidecar")
    if ENFORCE_PROJECT_FILTER and PROJECT_ID:
        return PROJECT_ID
    return requested


def _assert_document_authorized(document: dict[str, Any]) -> None:
    scope = document.get("scope")
    document_project_id = document.get("project_id")
    if scope == "global":
        return
    if ENFORCE_PROJECT_FILTER and PROJECT_ID and document_project_id != PROJECT_ID:
        raise ValueError("knowledge document is not authorized for this MCP sidecar")


def _platform_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if PLATFORM_API_KEY:
        headers[API_KEY_HEADER] = PLATFORM_API_KEY
    return headers


async def _platform_get(path: str) -> dict[str, Any] | list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=PLATFORM_API_URL, timeout=60, headers=_platform_headers()) as client:
        response = await client.get(path)
        if response.status_code >= 400:
            raise RuntimeError(f"platform API {path} failed: {response.status_code} {response.text[-1000:]}")
        return response.json()


async def _platform_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=PLATFORM_API_URL, timeout=60, headers=_platform_headers()) as client:
        response = await client.post(path, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"platform API {path} failed: {response.status_code} {response.text[-1000:]}")
        return response.json()


def _required_audit_run_id() -> str:
    if not AUDIT_RUN_ID:
        raise ValueError("AUDIT_RUN_ID is required for sandbox tools")
    return AUDIT_RUN_ID


def _validate_http_target(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an absolute http(s) URL")
    host = parsed.hostname.lower()
    if HTTP_TEST_ALLOWED_HOSTS and host not in HTTP_TEST_ALLOWED_HOSTS:
        raise ValueError("host is not allowed by HTTP_TEST_ALLOWED_HOSTS")
    if host in HTTP_TEST_BLOCKED_HOSTS:
        raise ValueError("host is blocked by http-test-mcp policy")
    return parsed


def _safe_response_headers(headers: httpx.Headers) -> dict[str, str]:
    blocked = {"set-cookie", "authorization", "proxy-authorization"}
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
