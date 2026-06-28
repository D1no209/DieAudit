import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tomllib
import xml.etree.ElementTree as ET
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
    for item in os.environ.get("HTTP_TEST_ALLOWED_HOSTS", "target").split(",")
    if item.strip()
}
HTTP_TEST_ALLOW_HOST_GATEWAY = os.environ.get("HTTP_TEST_ALLOW_HOST_GATEWAY", "false").lower() in {"1", "true", "yes"}
HTTP_TEST_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "docker-socket-proxy", "localhost"}
if not HTTP_TEST_ALLOW_HOST_GATEWAY:
    HTTP_TEST_BLOCKED_HOSTS.update({"host.docker.internal", "host.containers.internal"})

mcp = FastMCP(MCP_NAME, host="0.0.0.0", port=8001, stateless_http=True)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"ok": True, "service": MCP_NAME, "workspace_root": str(WORKSPACE_ROOT)})


@mcp.custom_route("/tools/capabilities", methods=["GET"])
async def capabilities_route(request):
    return JSONResponse(tool_capabilities())


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


@mcp.custom_route("/tools/whiteboard_create_card", methods=["POST"])
async def whiteboard_create_card_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_create_card(**body))


@mcp.custom_route("/tools/whiteboard_update_card", methods=["POST"])
async def whiteboard_update_card_route(request):
    body = await request.json()
    card_id = body.pop("card_id", "")
    return JSONResponse(await whiteboard_update_card(card_id=card_id, **body))


@mcp.custom_route("/tools/whiteboard_link_cards", methods=["POST"])
async def whiteboard_link_cards_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_link_cards(**body))


@mcp.custom_route("/tools/whiteboard_add_note", methods=["POST"])
async def whiteboard_add_note_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_add_note(**body))


@mcp.custom_route("/tools/whiteboard_list_graph", methods=["POST"])
async def whiteboard_list_graph_route(request):
    return JSONResponse(await whiteboard_list_graph())


@mcp.custom_route("/tools/whiteboard_find_attach_points", methods=["POST"])
async def whiteboard_find_attach_points_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_find_attach_points(query=body.get("query", ""), limit=int(body.get("limit", 10))))


@mcp.custom_route("/tools/whiteboard_search_cards", methods=["POST"])
async def whiteboard_search_cards_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_search_cards(**body))


@mcp.custom_route("/tools/whiteboard_declare_gap", methods=["POST"])
async def whiteboard_declare_gap_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_declare_gap(**body))


@mcp.custom_route("/tools/whiteboard_submit_chain_evidence", methods=["POST"])
async def whiteboard_submit_chain_evidence_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_submit_chain_evidence(**body))


@mcp.custom_route("/tools/whiteboard_schedule_agent", methods=["POST"])
async def whiteboard_schedule_agent_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_schedule_agent(**body))


@mcp.custom_route("/tools/whiteboard_subscribe_changes", methods=["POST"])
async def whiteboard_subscribe_changes_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_subscribe_changes(**body))


@mcp.custom_route("/tools/whiteboard_list_notifications", methods=["POST"])
async def whiteboard_list_notifications_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_list_notifications(**body))


@mcp.custom_route("/tools/whiteboard_mark_notification", methods=["POST"])
async def whiteboard_mark_notification_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_mark_notification(**body))


@mcp.custom_route("/tools/whiteboard_request_agent_help", methods=["POST"])
async def whiteboard_request_agent_help_route(request):
    body = await request.json()
    return JSONResponse(await whiteboard_request_agent_help(**body))


@mcp.custom_route("/tools/read_common_structure", methods=["POST"])
async def read_common_structure_route(request):
    return JSONResponse(read_common_structure())


@mcp.custom_route("/tools/start_sandbox_service", methods=["POST"])
async def start_sandbox_service_route(request):
    body = await request.json()
    return JSONResponse(await start_sandbox_service(**body))


@mcp.custom_route("/tools/codeql_query", methods=["POST"])
async def codeql_query_route(request):
    body = await request.json()
    return JSONResponse(
        codeql_query(
            database=body.get("database", ""),
            query=body.get("query", ""),
            timeout_seconds=int(body.get("timeout_seconds", 300)),
        )
    )


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
    evidence = _command_evidence("semgrep", command, timeout_seconds=timeout_seconds, output_path=output_path)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "available": True,
            **evidence,
            "timeout_seconds": timeout_seconds,
            "error": "semgrep scan timed out",
            "stdout": _tail_text(exc.stdout),
            "stderr": _tail_text(exc.stderr),
            "artifact_path": str(output_path) if output_path.exists() else None,
            "artifact": _artifact_evidence(output_path),
            "findings": [],
        }
    if result.returncode not in {0, 1}:
        return {
            "ok": False,
            "available": True,
            **evidence,
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "artifact_path": str(output_path) if output_path.exists() else None,
            "artifact": _artifact_evidence(output_path),
            "findings": [],
        }
    parsed = _load_json_artifact(output_path) if output_format == "json" else None
    findings = _semgrep_findings(parsed) if parsed else []
    return {
        "ok": True,
        "available": True,
        **evidence,
        "exit_code": result.returncode,
        "artifact_path": str(output_path),
        "artifact": _artifact_evidence(output_path),
        "findings": findings,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def tool_capabilities(required: list[str] | None = None) -> dict[str, Any]:
    tools = required or ["rg", "semgrep", "syft", "codeql"]
    binaries: dict[str, dict[str, Any]] = {}
    for tool in tools:
        binaries[tool] = _tool_binary_info(tool)
    return {
        "ok": all(item["available"] for item in binaries.values()),
        "service": MCP_NAME,
        "binaries": binaries,
    }


def _tool_binary_info(tool: str) -> dict[str, Any]:
    path = shutil.which(tool)
    info: dict[str, Any] = {"available": bool(path), "path": path, "version": None}
    if not path:
        return info
    for args in ([path, "--version"], [path, "version"]):
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0 and output:
            info["version"] = output.splitlines()[0][:200]
            break
    return info


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
    evidence = _command_evidence("syft", command, timeout_seconds=timeout_seconds, output_path=output_path)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "available": True,
            **evidence,
            "timeout_seconds": timeout_seconds,
            "error": "syft sbom generation timed out",
            "stdout": _tail_text(exc.stdout),
            "stderr": _tail_text(exc.stderr),
            "artifact_path": None,
            "artifact": _artifact_evidence(output_path),
        }
    if result.returncode != 0:
        return {
            "ok": False,
            "available": True,
            **evidence,
            "exit_code": result.returncode,
            "stderr": result.stderr[-4000:],
            "artifact_path": None,
            "artifact": _artifact_evidence(output_path),
        }
    output_path.write_text(result.stdout, encoding="utf-8")
    return {
        "ok": True,
        "available": True,
        **evidence,
        "exit_code": result.returncode,
        "artifact_path": str(output_path),
        "artifact": _artifact_evidence(output_path),
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
async def create_card(
    title: str,
    content: str = "",
    card_type: str = "observation",
    status: str = "open",
    confidence: str | None = None,
    finding_id: str | None = None,
    file_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    requirements: list[str] | None = None,
    expected_predecessors: list[dict[str, Any]] | None = None,
    possible_successors: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a shared audit-run Whiteboard card."""
    return await whiteboard_create_card(
        title=title,
        content=content,
        card_type=card_type,
        status=status,
        confidence=confidence,
        finding_id=finding_id,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        requirements=requirements or [],
        expected_predecessors=expected_predecessors or [],
        possible_successors=possible_successors or [],
        attachments=attachments or [],
        metadata=metadata or {},
    )


@mcp.tool()
async def update_card(card_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update a shared audit-run Whiteboard card."""
    return await whiteboard_update_card(card_id=card_id, **(updates or {}))


@mcp.tool()
async def link_cards(
    source_card_id: str,
    target_card_id: str,
    edge_type: str = "supports",
    rationale: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Connect two Whiteboard cards with a typed edge."""
    return await whiteboard_link_cards(
        source_card_id=source_card_id,
        target_card_id=target_card_id,
        edge_type=edge_type,
        rationale=rationale,
        metadata=metadata or {},
    )


@mcp.tool()
async def add_note(content: str, card_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add a side note to the Whiteboard or one card."""
    return await whiteboard_add_note(content=content, card_id=card_id, metadata=metadata or {})


@mcp.tool()
async def list_graph() -> dict[str, Any]:
    """Read the current audit-run Whiteboard graph."""
    return await whiteboard_list_graph()


@mcp.tool()
async def search_cards(
    query: str = "",
    card_type: str | None = None,
    status: str | None = None,
    finding_id: str | None = None,
    file_path: str | None = None,
    candidate_status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search Whiteboard cards by keyword and structured filters."""
    return await whiteboard_search_cards(
        query=query,
        card_type=card_type,
        status=status,
        finding_id=finding_id,
        file_path=file_path,
        candidate_status=candidate_status,
        limit=limit,
    )


@mcp.tool()
async def find_attach_points(query: str, limit: int = 10) -> dict[str, Any]:
    """Find candidate cards that this new evidence may attach to."""
    return await whiteboard_find_attach_points(query=query, limit=limit)


@mcp.tool()
async def declare_gap(
    title: str,
    content: str,
    gap_kind: str = "source",
    requirements: list[str] | None = None,
    finding_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Declare a Whiteboard gap that the swarm can automatically schedule."""
    merged_metadata = {"gap_kind": gap_kind, **(metadata or {})}
    return await whiteboard_declare_gap(
        title=title,
        content=content,
        requirements=requirements or [],
        finding_id=finding_id,
        metadata=merged_metadata,
    )


@mcp.tool()
async def schedule_agent(
    agent_name: str,
    goal: str,
    gap_card_id: str | None = None,
    finding_id: str | None = None,
    extra_input: dict[str, Any] | None = None,
    allow_external_network: bool = False,
) -> dict[str, Any]:
    """Ask the platform to start another AgentRun for this AuditRun."""
    return await whiteboard_schedule_agent(
        agent_name=agent_name,
        goal=goal,
        gap_card_id=gap_card_id,
        finding_id=finding_id,
        extra_input=extra_input or {},
        allow_external_network=allow_external_network,
    )


@mcp.tool()
async def subscribe_changes(
    filter: dict[str, Any],
    subscriber_task_id: str | None = None,
    subscriber_agent_run_id: str | None = None,
) -> dict[str, Any]:
    """Subscribe this long-running Agent to Whiteboard changes."""
    return await whiteboard_subscribe_changes(
        filter=filter,
        subscriber_task_id=subscriber_task_id,
        subscriber_agent_run_id=subscriber_agent_run_id,
    )


@mcp.tool()
async def list_notifications(status: str | None = "pending") -> dict[str, Any]:
    """List persisted Whiteboard notifications for this Agent."""
    return await whiteboard_list_notifications(status=status)


@mcp.tool()
async def mark_notification(notification_id: str, status: str, lease_seconds: int | None = None) -> dict[str, Any]:
    """Mark a Whiteboard notification as claimed, handled, or ignored."""
    return await whiteboard_mark_notification(notification_id=notification_id, status=status, lease_seconds=lease_seconds)


@mcp.tool()
async def request_agent_help(
    goal: str,
    reason: str,
    related_card_ids: list[str] | None = None,
    suggested_agent_name: str | None = None,
) -> dict[str, Any]:
    """Request controller approval before adding more Agent capacity."""
    return await whiteboard_request_agent_help(
        goal=goal,
        reason=reason,
        related_card_ids=related_card_ids or [],
        suggested_agent_name=suggested_agent_name,
    )


@mcp.tool()
def read_structure() -> dict[str, Any]:
    """Read the shared STRUCTURE.md generated for this AuditRun."""
    return read_common_structure()


@mcp.tool()
async def submit_chain_evidence(
    card_ids: list[str],
    edge_ids: list[str] | None = None,
    finding_id: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Submit a complete Whiteboard card chain as platform Evidence."""
    return await whiteboard_submit_chain_evidence(card_ids=card_ids, edge_ids=edge_ids or [], finding_id=finding_id, summary=summary)


async def whiteboard_create_card(**body: Any) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    body.setdefault("author", MCP_NAME)
    body.setdefault("agent_run_id", os.environ.get("AGENT_RUN_ID"))
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/cards", body)


async def whiteboard_update_card(card_id: str, **body: Any) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    if not card_id:
        raise ValueError("card_id is required")
    return await _platform_request("PATCH", f"/audit-runs/{audit_run_id}/whiteboard/cards/{card_id}", body)


async def whiteboard_link_cards(**body: Any) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    body.setdefault("author", MCP_NAME)
    body.setdefault("agent_run_id", os.environ.get("AGENT_RUN_ID"))
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/edges", body)


async def whiteboard_add_note(**body: Any) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    body.setdefault("author", MCP_NAME)
    body.setdefault("agent_run_id", os.environ.get("AGENT_RUN_ID"))
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/notes", body)


async def whiteboard_list_graph() -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    return await _platform_get(f"/audit-runs/{audit_run_id}/whiteboard")


async def whiteboard_search_cards(**body: Any) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/search", body)


async def whiteboard_find_attach_points(query: str, limit: int = 10) -> dict[str, Any]:
    result = await whiteboard_search_cards(query=query, limit=limit)
    return {"query": query, "matches": result.get("matches", [])}


async def whiteboard_declare_gap(**body: Any) -> dict[str, Any]:
    body["card_type"] = "gap"
    body.setdefault("status", "open")
    return await whiteboard_create_card(**body)


async def whiteboard_submit_chain_evidence(**body: Any) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/evidence", body)


async def whiteboard_schedule_agent(
    agent_name: str,
    goal: str,
    gap_card_id: str | None = None,
    finding_id: str | None = None,
    extra_input: dict[str, Any] | None = None,
    allow_external_network: bool = False,
) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    if not agent_name.strip():
        raise ValueError("agent_name is required")
    if not goal.strip():
        raise ValueError("goal is required")
    audit_run = await _platform_get(f"/audit-runs/{audit_run_id}")
    if not isinstance(audit_run, dict):
        raise ValueError("audit run lookup returned an invalid response")
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    workspace_path = config.get("workspace_host_path")
    project_id = str(audit_run.get("project_id") or PROJECT_ID or "")
    if not project_id:
        raise ValueError("project_id is required")
    task_card = await whiteboard_create_card(
        title=f"Scheduled Agent: {agent_name}",
        card_type="agent-task",
        status="scheduled",
        content=goal,
        finding_id=finding_id,
        metadata={"gap_card_id": gap_card_id, "scheduled_by": MCP_NAME, "scheduler_agent_run_id": os.environ.get("AGENT_RUN_ID")},
    )
    payload = {
        "audit_run_id": audit_run_id,
        "project_id": project_id,
        "agent_name": agent_name,
        "workspace_host_path": workspace_path,
        "allow_external_network": allow_external_network,
        "retain_runtime_on_failure": bool(audit_run.get("retain_runtime_on_failure")),
        "input_payload": {
            "goal": goal,
            "long_running": True,
            "agent_lifecycle": "long-running",
            "audit_phase": "whiteboard-swarm",
            "whiteboard": {
                "scheduled_by_card_id": task_card.get("card_id"),
                "gap_card_id": gap_card_id,
                "finding_id": finding_id,
                "instruction": "Read the Whiteboard, subscribe to relevant card or keyword changes, add cards/edges/notes for findings, request help through the schedule-request flow, and submit chain evidence when complete.",
            },
            **(extra_input or {}),
        },
    }
    result = await _platform_post(f"/audit-runs/{audit_run_id}/agent-runs", payload)
    await whiteboard_update_card(
        card_id=str(task_card.get("card_id") or ""),
        status="running",
        metadata={
            "gap_card_id": gap_card_id,
            "agent_result": result,
            "scheduled_by": MCP_NAME,
            "scheduler_agent_run_id": os.environ.get("AGENT_RUN_ID"),
        },
    )
    return {"ok": True, "task_card": task_card, "agent_run": result}


async def whiteboard_subscribe_changes(
    filter: dict[str, Any],
    subscriber_task_id: str | None = None,
    subscriber_agent_run_id: str | None = None,
) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    payload = {
        "filter": filter or {},
        "subscriber_task_id": subscriber_task_id or os.environ.get("WHITEBOARD_TASK_ID"),
        "subscriber_agent_run_id": subscriber_agent_run_id or os.environ.get("AGENT_RUN_ID"),
    }
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/subscriptions", payload)


async def whiteboard_list_notifications(status: str | None = "pending") -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    params = []
    if status:
        params.append(f"status={status}")
    agent_run_id = os.environ.get("AGENT_RUN_ID")
    if agent_run_id:
        params.append(f"subscriber_agent_run_id={agent_run_id}")
    suffix = "?" + "&".join(params) if params else ""
    notifications = await _platform_get(f"/audit-runs/{audit_run_id}/whiteboard/notifications{suffix}")
    return {"notifications": notifications, "count": len(notifications) if isinstance(notifications, list) else 0}


async def whiteboard_mark_notification(notification_id: str, status: str, lease_seconds: int | None = None) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    if not notification_id:
        raise ValueError("notification_id is required")
    return await _platform_post(
        f"/audit-runs/{audit_run_id}/whiteboard/notifications/{notification_id}",
        {
            "status": status,
            "claimed_by_agent_run_id": os.environ.get("AGENT_RUN_ID"),
            **({"lease_seconds": lease_seconds} if lease_seconds else {}),
        },
    )


async def whiteboard_request_agent_help(
    goal: str,
    reason: str,
    related_card_ids: list[str] | None = None,
    suggested_agent_name: str | None = None,
) -> dict[str, Any]:
    audit_run_id = _required_audit_run_id()
    if not goal.strip():
        raise ValueError("goal is required")
    payload = {
        "goal": goal,
        "reason": reason,
        "related_card_ids": related_card_ids or [],
        "suggested_agent_name": suggested_agent_name,
        "requested_by_task_id": os.environ.get("WHITEBOARD_TASK_ID"),
        "requested_by_agent_run_id": os.environ.get("AGENT_RUN_ID"),
    }
    return await _platform_post(f"/audit-runs/{audit_run_id}/whiteboard/schedule-requests", payload)


def read_common_structure() -> dict[str, Any]:
    path = ARTIFACT_ROOT / "common" / _required_audit_run_id() / "STRUCTURE.md"
    if not path.is_file():
        return {
            "ok": False,
            "available": False,
            "path": str(path),
            "error": "STRUCTURE.md is not available for this AuditRun yet",
        }
    return {"ok": True, "available": True, "path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")}


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


@mcp.tool()
def codeql_query(database: str, query: str, timeout_seconds: int = 300) -> dict[str, Any]:
    """Run a CodeQL query when CodeQL is installed in this MCP image."""
    codeql = shutil.which("codeql")
    if not codeql:
        return _tool_unavailable("codeql", "codeql executable is not installed in this MCP image")
    if not database or not query:
        raise ValueError("database and query are required")
    database_path = _safe_path(database)
    query_path = _safe_path(query)
    artifact_dir = _artifact_dir("codeql")
    output_path = artifact_dir / "codeql-query.bqrs"
    command = [
        codeql,
        "query",
        "run",
        str(query_path),
        "--database",
        str(database_path),
        "--output",
        str(output_path),
    ]
    return _run_tool_command("codeql", command, output_path, timeout_seconds)


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
    packages = [
        *_npm_package_lock(),
        *_yarn_lock(),
        *_pnpm_lock(),
        *_python_requirements(),
        *_python_pyproject(),
        *_python_poetry_lock(),
        *_go_mod(),
        *_cargo_lock(),
        *_composer_lock(),
        *_maven_pom(),
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


def _npm_package_lock() -> list[dict[str, Any]]:
    result = []
    for lockfile in WORKSPACE_ROOT.rglob("package-lock.json"):
        if not _is_safe_file(lockfile):
            continue
        try:
            data = json.loads(lockfile.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        manifest = lockfile.relative_to(WORKSPACE_ROOT).as_posix()
        for path, body in (data.get("packages") or {}).items():
            if path.startswith("node_modules/") and isinstance(body, dict):
                name = body.get("name") or path.removeprefix("node_modules/")
                version = body.get("version")
                if name and version:
                    result.append(_package("npm", name, version, manifest))
        _collect_npm_dependencies(data.get("dependencies") or {}, manifest, result)
    return result


def _collect_npm_dependencies(dependencies: dict[str, Any], manifest: str, result: list[dict[str, Any]]) -> None:
    for name, body in dependencies.items():
        if not isinstance(body, dict):
            continue
        version = body.get("version")
        if name and version:
            result.append(_package("npm", name, version, manifest))
        nested = body.get("dependencies")
        if isinstance(nested, dict):
            _collect_npm_dependencies(nested, manifest, result)


def _yarn_lock() -> list[dict[str, Any]]:
    result = []
    for lockfile in WORKSPACE_ROOT.rglob("yarn.lock"):
        if not _is_safe_file(lockfile):
            continue
        manifest = lockfile.relative_to(WORKSPACE_ROOT).as_posix()
        current_name: str | None = None
        current_version: str | None = None
        for raw_line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.rstrip()
            if line and not line.startswith((" ", "\t")) and line.endswith(":"):
                if current_name and current_version:
                    result.append(_package("npm", current_name, current_version, manifest))
                current_name = _npm_name_from_descriptor(line[:-1].split(",", 1)[0].strip().strip('"'))
                current_version = None
            elif current_name:
                match = re.match(r'^\s+version\s+"?([^"\s]+)"?', line)
                if match:
                    current_version = match.group(1)
        if current_name and current_version:
            result.append(_package("npm", current_name, current_version, manifest))
    return result


def _pnpm_lock() -> list[dict[str, Any]]:
    result = []
    pattern = re.compile(r"^\s{2,}/?((?:@[^/\s]+/)?[^@\s/]+)@([^:\s(]+)")
    for lockfile in WORKSPACE_ROOT.rglob("pnpm-lock.yaml"):
        if not _is_safe_file(lockfile):
            continue
        manifest = lockfile.relative_to(WORKSPACE_ROOT).as_posix()
        for line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line)
            if match:
                result.append(_package("npm", match.group(1), match.group(2), manifest))
    return result


def _python_requirements() -> list[dict[str, Any]]:
    result = []
    pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*={2,3}\s*([A-Za-z0-9_.!+-]+)")
    for requirements in WORKSPACE_ROOT.rglob("requirements*.txt"):
        if not _is_safe_file(requirements):
            continue
        manifest = requirements.relative_to(WORKSPACE_ROOT).as_posix()
        for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line)
            if not match:
                continue
            result.append(_package("PyPI", match.group(1), match.group(2), manifest))
    return result


def _python_pyproject() -> list[dict[str, Any]]:
    result = []
    for pyproject in WORKSPACE_ROOT.rglob("pyproject.toml"):
        if not _is_safe_file(pyproject):
            continue
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        except tomllib.TOMLDecodeError:
            continue
        manifest = pyproject.relative_to(WORKSPACE_ROOT).as_posix()
        for spec in (data.get("project") or {}).get("dependencies") or []:
            parsed = _python_exact_requirement(str(spec))
            if parsed:
                result.append(_package("PyPI", parsed[0], parsed[1], manifest))
        poetry_dependencies = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        for name, spec in poetry_dependencies.items():
            if str(name).lower() == "python":
                continue
            version = _poetry_dependency_version(spec)
            if version:
                result.append(_package("PyPI", name, version, manifest))
    return result


def _python_poetry_lock() -> list[dict[str, Any]]:
    result = []
    for lockfile in WORKSPACE_ROOT.rglob("poetry.lock"):
        if not _is_safe_file(lockfile):
            continue
        manifest = lockfile.relative_to(WORKSPACE_ROOT).as_posix()
        name = None
        version = None
        for line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() == "[[package]]":
                if name and version:
                    result.append(_package("PyPI", name, version, manifest))
                name = None
                version = None
            elif line.startswith("name = "):
                name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("version = "):
                version = line.split("=", 1)[1].strip().strip('"')
        if name and version:
            result.append(_package("PyPI", name, version, manifest))
    return result


def _go_mod() -> list[dict[str, Any]]:
    result = []
    pattern = re.compile(r"^\s*([A-Za-z0-9_.~/-]+)\s+(v[^\s]+)")
    for gomod in WORKSPACE_ROOT.rglob("go.mod"):
        if not _is_safe_file(gomod):
            continue
        manifest = gomod.relative_to(WORKSPACE_ROOT).as_posix()
        for line in gomod.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "module ", "go ", "require (", ")")):
                continue
            if stripped.startswith("require "):
                stripped = stripped.removeprefix("require ").strip()
            match = pattern.match(stripped)
            if match:
                result.append(_package("Go", match.group(1), match.group(2), manifest))
    return result


def _cargo_lock() -> list[dict[str, Any]]:
    result = []
    for lockfile in WORKSPACE_ROOT.rglob("Cargo.lock"):
        if not _is_safe_file(lockfile):
            continue
        manifest = lockfile.relative_to(WORKSPACE_ROOT).as_posix()
        name = None
        version = None
        for line in lockfile.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() == "[[package]]":
                if name and version:
                    result.append(_package("crates.io", name, version, manifest))
                name = None
                version = None
            elif line.startswith("name = "):
                name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("version = "):
                version = line.split("=", 1)[1].strip().strip('"')
        if name and version:
            result.append(_package("crates.io", name, version, manifest))
    return result


def _composer_lock() -> list[dict[str, Any]]:
    result = []
    for lockfile in WORKSPACE_ROOT.rglob("composer.lock"):
        if not _is_safe_file(lockfile):
            continue
        try:
            data = json.loads(lockfile.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        manifest = lockfile.relative_to(WORKSPACE_ROOT).as_posix()
        for body in [*(data.get("packages") or []), *(data.get("packages-dev") or [])]:
            name = body.get("name") if isinstance(body, dict) else None
            version = body.get("version") if isinstance(body, dict) else None
            if name and version:
                result.append(_package("Packagist", name, str(version).lstrip("v"), manifest))
    return result


def _maven_pom() -> list[dict[str, Any]]:
    result = []
    for pom in WORKSPACE_ROOT.rglob("pom.xml"):
        if not _is_safe_file(pom):
            continue
        try:
            root = ET.fromstring(pom.read_text(encoding="utf-8", errors="replace"))
        except ET.ParseError:
            continue
        manifest = pom.relative_to(WORKSPACE_ROOT).as_posix()
        properties = _maven_properties(root)
        for dep in root.findall(".//{*}dependencies/{*}dependency"):
            group_id = _xml_child_text(dep, "groupId")
            artifact_id = _xml_child_text(dep, "artifactId")
            version = _resolve_maven_property(_xml_child_text(dep, "version"), properties)
            if group_id and artifact_id and version:
                result.append(_package("Maven", f"{group_id}:{artifact_id}", version, manifest))
    return result


def _package(ecosystem: str, name: str, version: str, manifest: str) -> dict[str, Any]:
    return {
        "ecosystem": ecosystem,
        "name": str(name).strip(),
        "version": str(version).strip(),
        "manifest": manifest,
    }


def _npm_name_from_descriptor(descriptor: str) -> str | None:
    descriptor = descriptor.strip().strip("'\"")
    if descriptor.startswith("@"):
        index = descriptor.rfind("@")
        return descriptor[:index] if index > 0 else None
    return descriptor.rsplit("@", 1)[0] if "@" in descriptor else descriptor or None


def _python_exact_requirement(spec: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*={2,3}\s*([A-Za-z0-9_.!+-]+)", spec)
    return (match.group(1), match.group(2)) if match else None


def _poetry_dependency_version(spec: Any) -> str | None:
    if isinstance(spec, str):
        if spec and not any(spec.startswith(prefix) for prefix in ("^", "~", ">", "<", "*")):
            return spec.strip("=")
        parsed = _python_exact_requirement(f"pkg{spec}" if spec.startswith("==") else f"pkg=={spec}")
        return parsed[1] if parsed and spec.startswith("==") else None
    if isinstance(spec, dict):
        return _poetry_dependency_version(spec.get("version"))
    return None


def _maven_properties(root: ET.Element) -> dict[str, str]:
    properties: dict[str, str] = {}
    for item in root.findall(".//{*}properties/*"):
        tag = item.tag.rsplit("}", 1)[-1]
        if item.text:
            properties[tag] = item.text.strip()
    return properties


def _xml_child_text(element: ET.Element, name: str) -> str | None:
    child = element.find(f"{{*}}{name}")
    return child.text.strip() if child is not None and child.text else None


def _resolve_maven_property(value: str | None, properties: dict[str, str]) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"\$\{([^}]+)}", value.strip())
    return properties.get(match.group(1)) if match else value.strip()


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
    return await _platform_request("GET", path)


async def _platform_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _platform_request("POST", path, payload)


async def _platform_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=PLATFORM_API_URL, timeout=60, headers=_platform_headers()) as client:
        response = await client.request(method, path, json=payload)
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
    if host in HTTP_TEST_BLOCKED_HOSTS:
        raise ValueError("host is blocked by http-test-mcp policy")
    literal_address = _ip_address_or_none(host)
    if literal_address and _blocked_network_address(literal_address):
        raise ValueError("host resolves to a blocked private or local address")
    if HTTP_TEST_ALLOWED_HOSTS and host not in HTTP_TEST_ALLOWED_HOSTS:
        raise ValueError("host is not allowed by HTTP_TEST_ALLOWED_HOSTS")
    if not HTTP_TEST_ALLOWED_HOSTS:
        _reject_private_http_target(host)
    return parsed


def _ip_address_or_none(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _reject_private_http_target(host: str) -> None:
    try:
        addresses = [ipaddress.ip_address(item[-1][0]) for item in socket.getaddrinfo(host, None)]
    except OSError as exc:
        raise ValueError(f"host cannot be resolved: {host}") from exc
    for address in addresses:
        if _blocked_network_address(address):
            raise ValueError("host resolves to a blocked private or local address")


def _blocked_network_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or address.is_private
    )


def _safe_response_headers(headers: httpx.Headers) -> dict[str, str]:
    blocked = {"set-cookie", "authorization", "proxy-authorization"}
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


def _tool_unavailable(tool: str, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "available": False,
        "tool": tool,
        "error": error,
        "artifact_path": None,
    }


def _command_evidence(
    tool: str,
    command: list[str],
    *,
    timeout_seconds: int | float,
    output_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "command": [str(item) for item in command],
        "cwd": str(WORKSPACE_ROOT),
        "timeout_seconds": timeout_seconds,
        "artifact": _artifact_evidence(output_path),
    }


def _artifact_evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists() or not path.is_file():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def _run_tool_command(
    tool: str,
    command: list[str],
    output_path: Path,
    timeout_seconds: int,
    *,
    stdout_path: Path | None = None,
    write_stdout: bool = True,
) -> dict[str, Any]:
    timeout_seconds = min(max(int(timeout_seconds), 5), 1800)
    evidence = _command_evidence(tool, command, timeout_seconds=timeout_seconds, output_path=output_path)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "available": True,
            **evidence,
            "error": f"{tool} command timed out",
            "stdout": _tail_text(exc.stdout),
            "stderr": _tail_text(exc.stderr),
            "artifact_path": None,
            "artifact": _artifact_evidence(output_path),
            "stdout_artifact_path": str(stdout_path) if stdout_path and stdout_path.exists() else None,
            "stdout_artifact": _artifact_evidence(stdout_path),
        }
    if result.stdout and write_stdout and not output_path.exists():
        output_path.write_text(result.stdout, encoding="utf-8", errors="replace")
    if stdout_path is not None:
        stdout_path.write_text(result.stdout or "", encoding="utf-8", errors="replace")
    return {
        "ok": result.returncode == 0,
        "available": True,
        **evidence,
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "artifact_path": str(output_path) if output_path.exists() else None,
        "artifact": _artifact_evidence(output_path),
        "stdout_artifact_path": str(stdout_path) if stdout_path and stdout_path.exists() else None,
        "stdout_artifact": _artifact_evidence(stdout_path),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
