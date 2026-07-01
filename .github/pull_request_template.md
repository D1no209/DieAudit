## Summary

- 

## Changes

- 

## Testing

- [ ] `python -m pytest`
- [ ] `python -m compileall services/platform/app services/mcp-tools services/agents/kimi-code-agent services/web-api/app services/platform-common/dieaudit_common services/database/alembic/versions`
- [ ] `bun run build` in `services/web-ui`
- [ ] `docker compose --profile core config --services`
- [ ] `docker compose --profile tools config --services`
- [ ] `git diff --check`

## Security / Runtime Notes

- [ ] No real API keys, model keys, private source snapshots, reports, or
      sensitive logs are included.
- [ ] Demo/mock behavior is not exposed on production paths.
- [ ] New Docker, Agent, MCP, sandbox, or network permissions are documented.

## Limitations

List known limitations or follow-up work.
