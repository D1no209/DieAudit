from __future__ import annotations

import json
from pathlib import Path

from app.services.dependency_scanner import DependencyScanner


def test_dependency_scanner_detects_common_language_manifests(tmp_path: Path) -> None:
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"name": "demo"},
                    "node_modules/express": {"version": "4.18.2"},
                    "node_modules/@scope/pkg": {"version": "1.2.3"},
                },
                "dependencies": {
                    "lodash": {"version": "4.17.21"},
                    "nested": {"version": "1.0.0", "dependencies": {"debug": {"version": "4.3.4"}}},
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text(
        """
"@babel/core@^7.20.0":
  version "7.24.0"

left-pad@^1.3.0:
  version "1.3.0"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text(
        """
lockfileVersion: '9.0'
packages:
  /axios@1.6.7:
    resolution: {integrity: sha512-demo}
  /@scope/tool@2.1.0:
    resolution: {integrity: sha512-demo}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("Django==4.2.10\nuvicorn[standard]===0.29.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = ["requests==2.31.0"]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "0.110.0"
starlette = { version = "==0.36.3" }
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "poetry.lock").write_text(
        """
[[package]]
name = "pydantic"
version = "2.7.1"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "go.mod").write_text(
        """
module example.com/demo
go 1.22
require (
    github.com/gin-gonic/gin v1.9.1
)
require golang.org/x/crypto v0.23.0
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "Cargo.lock").write_text(
        """
[[package]]
name = "serde"
version = "1.0.197"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "composer.lock").write_text(
        json.dumps({"packages": [{"name": "monolog/monolog", "version": "2.9.2"}], "packages-dev": []}),
        encoding="utf-8",
    )
    (tmp_path / "pom.xml").write_text(
        """
<project>
  <properties>
    <junit.version>4.13.2</junit.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>${junit.version}</version>
    </dependency>
  </dependencies>
</project>
""".strip(),
        encoding="utf-8",
    )

    packages = DependencyScanner(str(tmp_path)).detect_dependencies()
    found = {(item["ecosystem"], item["name"], item["version"], item["manifest"]) for item in packages}

    assert ("npm", "express", "4.18.2", "package-lock.json") in found
    assert ("npm", "@scope/pkg", "1.2.3", "package-lock.json") in found
    assert ("npm", "lodash", "4.17.21", "package-lock.json") in found
    assert ("npm", "debug", "4.3.4", "package-lock.json") in found
    assert ("npm", "@babel/core", "7.24.0", "yarn.lock") in found
    assert ("npm", "left-pad", "1.3.0", "yarn.lock") in found
    assert ("npm", "axios", "1.6.7", "pnpm-lock.yaml") in found
    assert ("npm", "@scope/tool", "2.1.0", "pnpm-lock.yaml") in found
    assert ("PyPI", "Django", "4.2.10", "requirements.txt") in found
    assert ("PyPI", "uvicorn", "0.29.0", "requirements.txt") in found
    assert ("PyPI", "requests", "2.31.0", "pyproject.toml") in found
    assert ("PyPI", "fastapi", "0.110.0", "pyproject.toml") in found
    assert ("PyPI", "starlette", "0.36.3", "pyproject.toml") in found
    assert ("PyPI", "pydantic", "2.7.1", "poetry.lock") in found
    assert ("Go", "github.com/gin-gonic/gin", "v1.9.1", "go.mod") in found
    assert ("Go", "golang.org/x/crypto", "v0.23.0", "go.mod") in found
    assert ("crates.io", "serde", "1.0.197", "Cargo.lock") in found
    assert ("Packagist", "monolog/monolog", "2.9.2", "composer.lock") in found
    assert ("Maven", "junit:junit", "4.13.2", "pom.xml") in found


def test_dependency_scanner_deduplicates_by_ecosystem_name_and_version(tmp_path: Path) -> None:
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {"node_modules/debug": {"version": "4.3.4"}},
                "dependencies": {"debug": {"version": "4.3.4"}},
            }
        ),
        encoding="utf-8",
    )

    packages = DependencyScanner(str(tmp_path)).detect_dependencies()
    debug_rows = [item for item in packages if item["ecosystem"] == "npm" and item["name"] == "debug" and item["version"] == "4.3.4"]

    assert len(debug_rows) == 1
