from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".ts",
    ".tsx",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "bin",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "target",
    "vendor",
}

RISK_BUCKETS = [
    ("entrypoints", ("main", "app", "server", "index", "bootstrap", "startup")),
    ("routes-and-controllers", ("route", "router", "controller", "handler", "endpoint", "api", "view")),
    ("auth-and-access-control", ("auth", "login", "session", "jwt", "oauth", "permission", "role", "acl", "policy")),
    ("database-and-injection", ("sql", "query", "repository", "dao", "mapper", "model", "schema", "db", "database")),
    ("file-upload-and-paths", ("upload", "download", "file", "path", "storage", "archive", "extract")),
    ("config-and-secrets", ("config", "setting", "env", "secret", "credential", "token", "key")),
]


@dataclass(frozen=True)
class CodeAuditTaskPlan:
    task_id: str
    title: str
    focus: str
    file_paths: list[str]
    risk_keywords: list[str]
    metadata: dict[str, Any]


class CodeAuditPlanner:
    def __init__(self, workspace_path: str | Path):
        self.workspace = Path(workspace_path).resolve()

    def plan(self, *, max_tasks: int = 8, max_files_per_task: int = 25) -> list[CodeAuditTaskPlan]:
        files = self._code_files()
        if not files:
            return []
        max_tasks = max(1, int(max_tasks))
        max_files_per_task = max(1, int(max_files_per_task))
        selected: set[str] = set()
        tasks: list[CodeAuditTaskPlan] = []
        for focus, keywords in RISK_BUCKETS:
            matches = [path for path in files if path not in selected and self._matches(path, keywords)]
            if not matches:
                continue
            for chunk in self._chunks(matches, max_files_per_task):
                tasks.append(
                    CodeAuditTaskPlan(
                        task_id=f"code-{len(tasks) + 1:03d}",
                        title=f"Code vulnerability analysis: {focus}",
                        focus=focus,
                        file_paths=chunk,
                        risk_keywords=list(keywords),
                        metadata={"selection": "risk_bucket", "file_count": len(chunk)},
                    )
                )
                selected.update(chunk)
                if len(tasks) >= max_tasks:
                    return tasks
        remaining = [path for path in files if path not in selected]
        for chunk in self._chunks(remaining, max_files_per_task):
            tasks.append(
                CodeAuditTaskPlan(
                    task_id=f"code-{len(tasks) + 1:03d}",
                    title="Code vulnerability analysis: general source batch",
                    focus="general-source",
                    file_paths=chunk,
                    risk_keywords=[],
                    metadata={"selection": "general_batch", "file_count": len(chunk)},
                )
            )
            if len(tasks) >= max_tasks:
                break
        return tasks

    def _code_files(self) -> list[str]:
        if not self.workspace.is_dir():
            return []
        files: list[str] = []
        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue
            if self._is_skipped(path):
                continue
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            try:
                relative = path.relative_to(self.workspace).as_posix()
            except ValueError:
                continue
            files.append(relative)
        return sorted(files, key=self._priority_key)

    def _is_skipped(self, path: Path) -> bool:
        lowered_parts = {part.lower() for part in path.relative_to(self.workspace).parts[:-1]}
        return bool(lowered_parts & SKIP_DIRS)

    @staticmethod
    def _matches(path: str, keywords: tuple[str, ...]) -> bool:
        lowered = path.lower()
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _chunks(items: list[str], size: int) -> list[list[str]]:
        return [items[index : index + size] for index in range(0, len(items), size)]

    @staticmethod
    def _priority_key(path: str) -> tuple[int, int, str]:
        lowered = path.lower()
        risk_score = 0
        for index, (_, keywords) in enumerate(RISK_BUCKETS):
            if any(keyword in lowered for keyword in keywords):
                risk_score = min(risk_score, -(len(RISK_BUCKETS) - index))
        depth = path.count("/")
        return (risk_score, depth, lowered)
