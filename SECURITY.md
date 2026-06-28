# Security Policy

DieAudit is a code audit platform that can execute tool containers, Agent
containers, sandbox targets, and AI-generated PoCs. Treat any deployment as a
security-sensitive system.

## Supported Versions

The project is pre-1.0. Security fixes are applied to the `main` branch.

## Reporting a Vulnerability

Please do not disclose exploitable vulnerabilities publicly before maintainers
have had time to investigate.

Report security issues by opening a private GitHub security advisory when
available, or by contacting the repository owner through GitHub.

Include:

- affected commit or version,
- affected component,
- reproduction steps,
- impact,
- logs or artifacts with secrets removed,
- whether the issue requires a malicious project, malicious Agent/MCP image, or
  network attacker.

Do not attach private source code, real customer audit reports, API keys, model
provider keys, or exploit payloads that target third-party systems.

## Deployment Guidance

- Keep API authentication enabled.
- Keep `ENABLE_DEMO_TEMPLATES=false` in production.
- Do not expose Docker, Postgres, Redis, NATS, or Qdrant ports to
  untrusted networks.
- Keep Agent and MCP containers away from the raw Docker socket.
- Treat ACP stdio MCPs as part of the agent trust boundary; install them only
  from pinned, reviewed image build inputs.
- Keep PoC external network access disabled unless explicitly required.
- Use dedicated hosts or VMs for high-risk audits.
- Rotate model/API keys that may have been exposed to Agent prompts, logs, or
  artifacts.

## Scope

In scope:

- authentication and authorization bypasses,
- Docker runtime escape through DieAudit configuration mistakes,
- cross-project or cross-AuditRun data access,
- artifact path traversal,
- unsafe default exposure of demo/mock components,
- stored secret leaks in UI, API, logs, or artifacts.

Out of scope:

- vulnerabilities in third-party tools when used outside DieAudit,
- model hallucinations that do not cross a security boundary,
- issues requiring direct administrator access to the deployment host,
- denial of service from intentionally huge projects beyond configured limits.
