from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIPPED_DIRS = {".git", ".pytest_cache", "__pycache__", "data", "dist", "node_modules"}
SCANNED_SUFFIXES = {
    "",
    ".css",
    ".dockerfile",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_PATTERNS = [
    re.compile(r"tp-[a-z0-9]{32,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{24,}"),
    re.compile(r"(?im)^\s*(?:anthropic|openai|local_llm)_api_key[ \t]*=[ \t]*(?!$|change-me\b)[^\s#]+"),
]


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        path = ROOT / line
        if not path.is_file():
            continue
        if SKIPPED_DIRS.intersection(Path(line).parts):
            continue
        if path.suffix.lower() in SCANNED_SUFFIXES or path.name in {".env.example", ".env.production.example", ".gitignore"}:
            files.append(path)
    return files


def test_repository_does_not_contain_committed_provider_secrets() -> None:
    findings: list[str] = []
    for path in _candidate_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(str(path.relative_to(ROOT)))

    assert not findings, f"possible committed secrets found in: {sorted(set(findings))}"


def test_local_env_file_is_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".env" in {line.strip() for line in gitignore.splitlines()}
