from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from httpx import Headers

import tool_mcp


def test_http_target_blocks_host_gateway() -> None:
    with pytest.raises(ValueError, match="blocked"):
        tool_mcp._validate_http_target("http://host.docker.internal:8080/health")


def test_http_target_blocks_control_plane_even_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "HTTP_TEST_ALLOWED_HOSTS", {"docker-socket-proxy"})

    with pytest.raises(ValueError, match="blocked"):
        tool_mcp._validate_http_target("http://docker-socket-proxy:2375/version")


def test_http_target_defaults_to_target_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "HTTP_TEST_ALLOWED_HOSTS", {"target"})

    assert tool_mcp._validate_http_target("http://target:8080").hostname == "target"
    with pytest.raises(ValueError, match="not allowed"):
        tool_mcp._validate_http_target("https://example.com")


def test_http_target_blocks_private_ip_literals_even_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "HTTP_TEST_ALLOWED_HOSTS", {"127.0.0.1", "10.0.0.5"})

    with pytest.raises(ValueError, match="private or local"):
        tool_mcp._validate_http_target("http://127.0.0.1:8080")
    with pytest.raises(ValueError, match="private or local"):
        tool_mcp._validate_http_target("http://10.0.0.5")


def test_http_target_blocks_private_dns_without_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "HTTP_TEST_ALLOWED_HOSTS", set())
    monkeypatch.setattr(tool_mcp.socket, "getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("10.0.0.5", 0))])

    with pytest.raises(ValueError, match="private or local"):
        tool_mcp._validate_http_target("https://example.test")


def test_http_target_requires_absolute_http_url() -> None:
    with pytest.raises(ValueError, match="absolute"):
        tool_mcp._validate_http_target("/relative/path")


def test_http_target_honors_allowed_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "HTTP_TEST_ALLOWED_HOSTS", {"target"})

    assert tool_mcp._validate_http_target("http://target:8080").hostname == "target"
    with pytest.raises(ValueError, match="not allowed"):
        tool_mcp._validate_http_target("http://other:8080")


def test_response_headers_strip_credentials() -> None:
    headers = Headers(
        {
            "content-type": "text/plain",
            "set-cookie": "session=secret",
            "authorization": "Bearer secret",
        }
    )

    safe = tool_mcp._safe_response_headers(headers)

    assert safe == {"content-type": "text/plain"}


def test_tool_capabilities_reports_requested_binaries() -> None:
    result = tool_mcp.tool_capabilities(["python", "definitely-not-a-dieaudit-tool"])

    assert result["binaries"]["python"]["available"] is True
    assert "version" in result["binaries"]["python"]
    assert result["binaries"]["definitely-not-a-dieaudit-tool"]["available"] is False
    assert result["ok"] is False


def test_semgrep_scan_returns_reproducible_command_and_artifact_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(tool_mcp, "ARTIFACT_ROOT", (tmp_path / "artifacts").resolve())
    monkeypatch.setattr(tool_mcp, "MCP_NAME", "semgrep-mcp")
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == "semgrep" else None)

    def fake_run(command, **_kwargs):
        output_path = Path(command[command.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"results": []}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="scan ok", stderr="")

    monkeypatch.setattr(tool_mcp.subprocess, "run", fake_run)

    result = tool_mcp.semgrep_scan(timeout_seconds=15)

    assert result["ok"] is True
    assert result["tool"] == "semgrep"
    assert result["command"][:3] == ["/usr/bin/semgrep", "scan", "--config"]
    assert result["cwd"] == str(tmp_path.resolve())
    assert result["artifact"]["exists"] is True
    assert result["artifact"]["size"] > 0


def test_generate_sbom_returns_reproducible_command_and_artifact_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(tool_mcp, "ARTIFACT_ROOT", (tmp_path / "artifacts").resolve())
    monkeypatch.setattr(tool_mcp, "MCP_NAME", "sca-mcp")
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == "syft" else None)
    monkeypatch.setattr(
        tool_mcp.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout='{"sbom": true}', stderr=""),
    )

    result = tool_mcp.generate_sbom(output_format="spdx-json", timeout_seconds=15)

    assert result["ok"] is True
    assert result["tool"] == "syft"
    assert result["command"] == ["/usr/bin/syft", str(tmp_path.resolve()), "-o", "spdx-json"]
    assert result["artifact"]["exists"] is True
    assert result["artifact"]["size"] == len('{"sbom": true}')


def test_run_tool_command_returns_trace_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())

    def fake_run(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=5, output="partial stdout", stderr="partial stderr")

    monkeypatch.setattr(tool_mcp.subprocess, "run", fake_run)

    result = tool_mcp._run_tool_command("codeql", ["codeql", "query", "run"], tmp_path / "query.bqrs", 5)

    assert result["ok"] is False
    assert result["tool"] == "codeql"
    assert result["command"] == ["codeql", "query", "run"]
    assert result["artifact"]["exists"] is False
    assert "timed out" in result["error"]


def test_run_tool_command_does_not_overwrite_existing_artifact_with_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    output_path = tmp_path / "result.txt"
    log_path = tmp_path / "result.log"

    def fake_run(command, **_kwargs):
        output_path.write_text("actual result", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="tool log", stderr="")

    monkeypatch.setattr(tool_mcp.subprocess, "run", fake_run)

    result = tool_mcp._run_tool_command(
        "joern",
        ["joern", "--script", "query.sc"],
        output_path,
        5,
        stdout_path=log_path,
        write_stdout=True,
    )

    assert result["ok"] is True
    assert output_path.read_text(encoding="utf-8") == "actual result"
    assert log_path.read_text(encoding="utf-8") == "tool log"


def test_joern_build_cpg_rejects_workspace_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(tool_mcp, "ARTIFACT_ROOT", (tmp_path / "artifacts").resolve())
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == "joern" else None)

    with pytest.raises(ValueError, match="escapes workspace"):
        tool_mcp.joern_build_cpg("../outside")


def test_joern_query_rejects_empty_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == "joern" else None)

    with pytest.raises(ValueError, match="query is required"):
        tool_mcp.joern_query("")


def test_joern_common_queries_runs_pack_and_records_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_root = (tmp_path / "artifacts").resolve()
    cpg_path = artifact_root / "joern-mcp" / "joern" / "cpg.bin.zip"
    cpg_path.parent.mkdir(parents=True, exist_ok=True)
    cpg_path.write_text("fake cpg", encoding="utf-8")
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(tool_mcp, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(tool_mcp, "MCP_NAME", "joern-mcp")
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == "joern" else None)

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="entrypoint result", stderr="")

    monkeypatch.setattr(tool_mcp.subprocess, "run", fake_run)

    result = tool_mcp.joern_common_queries(str(cpg_path), "entrypoints", timeout_seconds=15)

    assert result["ok"] is True
    assert result["tool"] == "joern"
    assert result["query_pack"] == "entrypoints"
    assert result["artifact"]["exists"] is True
    assert result["artifact_path"].endswith("joern-query-entrypoints.txt")


def test_joern_query_imports_cpg_from_artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = (tmp_path / "workspace").resolve()
    artifact_root = (tmp_path / "artifacts").resolve()
    cpg_path = artifact_root / "joern-mcp" / "joern" / "cpg.bin.zip"
    workspace_root.mkdir(parents=True)
    cpg_path.parent.mkdir(parents=True)
    cpg_path.write_text("fake cpg", encoding="utf-8")
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(tool_mcp, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(tool_mcp, "MCP_NAME", "joern-mcp")
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool == "joern" else None)

    captured: dict[str, str] = {}

    def fake_run(command, **_kwargs):
        script_path = Path(command[command.index("--script") + 1])
        captured["script"] = script_path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="query result", stderr="")

    monkeypatch.setattr(tool_mcp.subprocess, "run", fake_run)

    result = tool_mcp.joern_query("cpg.method.take(1).size", cpg_path=str(cpg_path), timeout_seconds=15)

    assert result["ok"] is True
    assert f'importCpg("{cpg_path.as_posix()}")' in captured["script"]


def test_joern_build_cpg_runs_query_packs_after_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(tool_mcp, "ARTIFACT_ROOT", (tmp_path / "artifacts").resolve())
    monkeypatch.setattr(tool_mcp, "MCP_NAME", "joern-mcp")
    monkeypatch.setattr(tool_mcp.shutil, "which", lambda tool: f"/usr/bin/{tool}" if tool in {"joern", "joern-parse"} else None)

    def fake_run(command, **_kwargs):
        if "joern-parse" in str(command[0]):
            Path(command[command.index("--output") + 1]).write_text("fake cpg", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="parse log that must not overwrite cpg", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="query result", stderr="")

    monkeypatch.setattr(tool_mcp.subprocess, "run", fake_run)

    result = tool_mcp.joern_build_cpg(".", timeout_seconds=30, query_packs=["entrypoints", "secrets"])

    assert result["ok"] is True
    assert result["artifact"]["exists"] is True
    assert Path(result["artifact_path"]).read_text(encoding="utf-8") == "fake cpg"
    assert result["stdout_artifact"]["exists"] is True
    assert Path(result["stdout_artifact_path"]).read_text(encoding="utf-8") == "parse log that must not overwrite cpg"
    assert [item["query_pack"] for item in result["query_packs"]] == ["entrypoints", "secrets"]
    assert result["query_packs"][0]["artifact_path"].endswith("joern-query-entrypoints.txt")
    assert result["query_packs"][1]["artifact_path"].endswith("joern-query-secrets.txt")


def test_detect_dependencies_covers_common_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "WORKSPACE_ROOT", tmp_path.resolve())
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/express": {"version": "4.18.2"}}, "dependencies": {}}),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text('"@babel/core@^7.20.0":\n  version "7.24.0"\n', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("packages:\n  /@scope/tool@2.1.0:\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("Django==4.2.10\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["requests==2.31.0"]\n', encoding="utf-8")
    (tmp_path / "go.mod").write_text("module demo\nrequire golang.org/x/crypto v0.23.0\n", encoding="utf-8")
    (tmp_path / "Cargo.lock").write_text('[[package]]\nname = "serde"\nversion = "1.0.197"\n', encoding="utf-8")
    (tmp_path / "composer.lock").write_text(
        json.dumps({"packages": [{"name": "monolog/monolog", "version": "2.9.2"}]}),
        encoding="utf-8",
    )
    (tmp_path / "pom.xml").write_text(
        """
<project>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
  </dependencies>
</project>
""".strip(),
        encoding="utf-8",
    )

    packages = tool_mcp._detect_dependencies()
    found = {(item["ecosystem"], item["name"], item["version"]) for item in packages}

    assert ("npm", "express", "4.18.2") in found
    assert ("npm", "@babel/core", "7.24.0") in found
    assert ("npm", "@scope/tool", "2.1.0") in found
    assert ("PyPI", "Django", "4.2.10") in found
    assert ("PyPI", "requests", "2.31.0") in found
    assert ("Go", "golang.org/x/crypto", "v0.23.0") in found
    assert ("crates.io", "serde", "1.0.197") in found
    assert ("Packagist", "monolog/monolog", "2.9.2") in found
    assert ("Maven", "junit:junit", "4.13.2") in found
