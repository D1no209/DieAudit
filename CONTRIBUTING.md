# Contributing to DieAudit

Thanks for considering a contribution.

DieAudit is security tooling, so correctness and honest runtime behavior matter
more than broad feature claims. Avoid mock behavior on production paths, and
prefer clear unavailable/error states over silent fallback.

## Development Setup

Install Python dependencies:

```powershell
python -m pip install -r services\platform\requirements.txt
python -m pip install -r services\mcp-tools\requirements.txt
python -m pip install pytest pytest-asyncio requests-mock time-machine
```

Install frontend dependencies:

```powershell
cd services\web-ui
npm ci
```

## Validation

Run these before opening a pull request:

```powershell
python -m pytest
python -m compileall services\platform\app services\mcp-tools services\agents\opencode-agent
cd services\web-ui
npm run build
```

From the repository root:

```powershell
docker compose --profile core config --services
docker compose --profile tools config --services
git diff --check
```

## Contribution Guidelines

- Keep production and demo/mock surfaces clearly separated.
- Use SQLAlchemy ORM for application persistence.
- Keep frontend pages decomposed into focused React components.
- Do not commit `.env`, API keys, model keys, source snapshots, reports, or
  runtime artifacts.
- Keep Agent handoff behavior compatible with per-finding `finding.md`
  workspaces.
- Add tests for backend behavior, pipeline state transitions, and frontend
  structure when changing those areas.
- Document new runtime requirements in README or `docs/`.

## Commit Style

Use concise imperative commit messages, for example:

```text
Add configurable audit run swarm settings
```

## Pull Requests

Each pull request should include:

- What changed.
- Why it changed.
- How it was tested.
- Any remaining limitations or unavailable runtime dependencies.

Do not include real vulnerability reports, private source code, model API keys,
or sensitive logs in public issues or pull requests.
