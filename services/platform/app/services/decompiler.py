from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKAGE_EXTENSIONS = {".jar", ".class", ".war", ".ear", ".apk", ".dex", ".dll", ".exe"}


@dataclass(frozen=True)
class DecompiledArtifact:
    artifact_id: str
    original_path: str
    sha256: str
    tool: str
    output_path: str
    workspace_output_path: str
    language_hint: str
    status: str
    error: str | None = None
    graph_indexable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "original_path": self.original_path,
            "sha256": self.sha256,
            "tool": self.tool,
            "output_path": self.output_path,
            "workspace_output_path": self.workspace_output_path,
            "language_hint": self.language_hint,
            "status": self.status,
            "error": self.error,
            "graph_indexable": self.graph_indexable,
        }


class DecompilerService:
    def __init__(
        self,
        workspace: str | Path,
        *,
        output_dir: str = ".dieaudit/decompiled",
        max_artifact_size_mb: int = 200,
        timeout_seconds: int = 300,
        max_artifacts: int = 50,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.output_root = (self.workspace / output_dir).resolve()
        self.output_dir = output_dir.replace("\\", "/").strip("/")
        self.max_artifact_size = max(1, int(max_artifact_size_mb)) * 1024 * 1024
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_artifacts = max(1, int(max_artifacts))

    def decompile(self) -> dict[str, Any]:
        self.output_root.mkdir(parents=True, exist_ok=True)
        artifacts = []
        for package in self._package_files()[: self.max_artifacts]:
            artifacts.append(self._decompile_one(package).to_dict())
        return {
            "enabled": True,
            "output_dir": self.output_dir,
            "artifacts": artifacts,
            "count": len(artifacts),
            "succeeded": sum(1 for item in artifacts if item.get("status") == "completed"),
            "failed": sum(1 for item in artifacts if item.get("status") == "failed"),
            "skipped": sum(1 for item in artifacts if item.get("status") == "skipped"),
        }

    def _package_files(self) -> list[Path]:
        ignored = {".git", "node_modules", ".venv", "__pycache__", "target", "dist"}
        packages: list[Path] = []
        if not self.workspace.is_dir():
            return packages
        for path in self.workspace.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in PACKAGE_EXTENSIONS:
                continue
            try:
                rel_parts = set(path.relative_to(self.workspace).parts)
            except ValueError:
                continue
            if ignored & rel_parts or self.output_root in path.parents:
                continue
            packages.append(path)
        return sorted(packages, key=lambda item: item.as_posix())

    def _decompile_one(self, package: Path) -> DecompiledArtifact:
        digest = self._sha256(package)
        artifact_id = f"{package.stem[:40]}-{digest[:12]}".replace(" ", "-")
        output = self.output_root / artifact_id
        rel_output = f"{self.output_dir}/{artifact_id}"
        rel_original = self._workspace_relative(package)
        kind = package.suffix.lower()
        tool, language = self._tool_for(kind)
        if package.stat().st_size > self.max_artifact_size:
            return DecompiledArtifact(artifact_id, rel_original, digest, tool, str(output), rel_output, language, "skipped", "artifact exceeds size limit")
        if not shutil.which(tool):
            return DecompiledArtifact(artifact_id, rel_original, digest, tool, str(output), rel_output, language, "skipped", f"{tool} is not installed")
        output.mkdir(parents=True, exist_ok=True)
        try:
            if kind in {".jar", ".class", ".war", ".ear"}:
                command = [tool, str(package), "--outputdir", str(output)]
            elif kind in {".apk", ".dex"}:
                command = [tool, "-d", str(output), str(package)]
            else:
                command = [tool, "-p", "-o", str(output), str(package)]
            completed = subprocess.run(command, cwd=self.workspace, text=True, capture_output=True, timeout=self.timeout_seconds)
            if completed.returncode != 0:
                error = (completed.stderr or completed.stdout or f"{tool} exited {completed.returncode}")[-4000:]
                return DecompiledArtifact(artifact_id, rel_original, digest, tool, str(output), rel_output, language, "failed", error)
            return DecompiledArtifact(artifact_id, rel_original, digest, tool, str(output), rel_output, language, "completed", graph_indexable=True)
        except Exception as exc:
            return DecompiledArtifact(artifact_id, rel_original, digest, tool, str(output), rel_output, language, "failed", str(exc))

    @staticmethod
    def _tool_for(suffix: str) -> tuple[str, str]:
        if suffix in {".jar", ".class", ".war", ".ear"}:
            return ("cfr", "java")
        if suffix in {".apk", ".dex"}:
            return ("jadx", "java")
        return ("ilspycmd", "csharp")

    def _workspace_relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.workspace).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
