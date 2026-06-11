from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_bootstrap_scripts_do_not_build_demo_by_default() -> None:
    ps1 = read_source("scripts/bootstrap.ps1")
    sh = read_source("scripts/bootstrap.sh")

    assert "param(" in ps1
    assert "[switch]$IncludeDemo" in ps1
    assert "if ($IncludeDemo)" in ps1
    assert "docker compose --profile core build" in ps1
    assert "docker compose --profile demo build" in ps1

    assert "--include-demo" in sh
    assert 'if [ "${include_demo}" = "true" ]' in sh
    assert "docker compose --profile core build" in sh
    assert "docker compose --profile demo build" in sh


def test_tool_pull_scripts_keep_mock_images_opt_in() -> None:
    ps1 = read_source("scripts/pull-tool-images.ps1")
    sh = read_source("scripts/pull-tool-images.sh")

    default_ps1_images = ps1.split("$images = @(", 1)[1].split(")", 1)[0]
    default_sh_images = sh.split("images=(", 1)[1].split(")", 1)[0]

    assert "dieaudit/mock-agent:local" not in default_ps1_images
    assert "dieaudit/mock-mcp:local" not in default_ps1_images
    assert "dieaudit/mock-agent:local" not in default_sh_images
    assert "dieaudit/mock-mcp:local" not in default_sh_images
    assert "mock-agent-image mock-mcp-image" in ps1
    assert "mock-agent-image mock-mcp-image" in sh


def test_readme_describes_demo_profile_as_explicit_opt_in() -> None:
    readme = read_source("README.md")

    assert "does not build or expose mock demo images unless explicitly requested" in readme
    assert "Demo fixtures are intentionally excluded from the default startup path" in readme
    assert ".\\scripts\\bootstrap.ps1 -IncludeDemo" in readme
    assert "./scripts/bootstrap.sh --include-demo" in readme
