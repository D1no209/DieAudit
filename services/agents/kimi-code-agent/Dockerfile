FROM python:3.12-slim

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1
ARG CODEBASE_MEMORY_MCP_VERSION=0.8.1

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}
ENV no_proxy=${NO_PROXY}
ENV BUN_INSTALL=/root/.bun
ENV PATH=/root/.bun/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV ACP_RUNTIME_NAME=kimi
ENV ACP_COMMAND=kimi-code
ENV ACP_ARGS="acp"
ENV KIMI_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir agent-client-protocol==0.10.1 fastapi==0.115.6 uvicorn==0.34.0 httpx==0.28.1

RUN curl -fsSL https://bun.sh/install | bash \
    && bun --version \
    && bunx --version \
    && bun install -g @moonshot-ai/kimi-code \
    && python -c "from pathlib import Path; path=Path('/root/.bun/install/global/node_modules/@moonshot-ai/kimi-code/dist/main.mjs'); text=path.read_text(encoding='utf-8'); old='async function harnessIsAuthed(harness) {\\n\\treturn (await harness.auth.status()).providers.some((entry) => entry.hasToken === true);\\n}\\n'; new='async function harnessIsAuthed(harness) {\\n\\tif ((process.env.KIMI_MODEL_NAME ?? \"\").trim().length > 0 && (process.env.KIMI_MODEL_API_KEY ?? \"\").trim().length > 0) return true;\\n\\treturn (await harness.auth.status()).providers.some((entry) => entry.hasToken === true);\\n}\\n'; assert old in text, 'Kimi ACP auth gate patch target not found'; path.write_text(text.replace(old, new), encoding='utf-8')" \
    && printf '#!/bin/sh\nexec /root/.bun/bin/bun /root/.bun/install/global/node_modules/@moonshot-ai/kimi-code/dist/main.mjs "$@"\n' > /usr/local/bin/kimi-code \
    && chmod +x /usr/local/bin/kimi-code \
    && kimi-code --version

RUN python -c "import os, shutil, tarfile, tempfile, urllib.request; \
version=os.environ.get('CODEBASE_MEMORY_MCP_VERSION', '${CODEBASE_MEMORY_MCP_VERSION}'); \
url=f'https://github.com/DeusData/codebase-memory-mcp/releases/download/v{version}/codebase-memory-mcp-linux-amd64.tar.gz'; \
archive='/tmp/codebase-memory-mcp.tar.gz'; \
urllib.request.urlretrieve(url, archive); \
tmp=tempfile.mkdtemp(prefix='cbm-'); \
tarfile.open(archive, 'r:gz').extractall(tmp); \
matches=[path for path in __import__('pathlib').Path(tmp).rglob('codebase-memory-mcp') if path.is_file()]; \
shutil.copyfile(str(matches[0]), '/usr/local/bin/codebase-memory-mcp')" \
    && chmod 755 /usr/local/bin/codebase-memory-mcp \
    && codebase-memory-mcp --version

COPY services/agents/opencode-agent/opencode_acp_runner.py /app/acp_runner.py
COPY services/agents/opencode-agent/opencode_acp_runner.py /app/opencode_acp_runner.py
COPY services/agents/opencode-agent/kimi_acp_runtime_server.py /app/kimi_acp_runtime_server.py

WORKDIR /workspace

CMD ["python", "/app/acp_runner.py"]
