from pathlib import Path

from app.services.code_analysis import CodeAuditPlanner


def test_code_audit_planner_prioritizes_risk_batches(tmp_path: Path) -> None:
    files = {
        "src/app.py": "app = create_app()",
        "src/routes/user_routes.py": "def route(): pass",
        "src/auth/jwt_service.py": "def verify(): pass",
        "src/db/query_builder.py": "def query(): pass",
        "src/static/readme.txt": "not code",
        "node_modules/pkg/index.js": "ignored",
        "dist/bundle.js": "ignored",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    tasks = CodeAuditPlanner(tmp_path).plan(max_tasks=4, max_files_per_task=2)

    assert [task.focus for task in tasks] == [
        "entrypoints",
        "routes-and-controllers",
        "auth-and-access-control",
        "database-and-injection",
    ]
    planned_files = {path for task in tasks for path in task.file_paths}
    assert "node_modules/pkg/index.js" not in planned_files
    assert "dist/bundle.js" not in planned_files
    assert "src/static/readme.txt" not in planned_files


def test_code_audit_planner_batches_general_source(tmp_path: Path) -> None:
    for index in range(5):
        path = tmp_path / "src" / f"module_{index}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def f(): pass", encoding="utf-8")

    tasks = CodeAuditPlanner(tmp_path).plan(max_tasks=3, max_files_per_task=2)

    assert [task.focus for task in tasks] == ["general-source", "general-source", "general-source"]
    assert [len(task.file_paths) for task in tasks] == [2, 2, 1]
