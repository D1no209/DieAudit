from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import Headers

import tool_mcp


def test_http_target_blocks_host_gateway() -> None:
    with pytest.raises(ValueError, match="blocked"):
        tool_mcp._validate_http_target("http://host.docker.internal:8080/health")


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
    assert result["binaries"]["definitely-not-a-dieaudit-tool"]["available"] is False
    assert result["ok"] is False


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
