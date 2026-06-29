FROM python:3.12-slim-trixie

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1
ARG CODEBASE_MEMORY_MCP_VERSION=0.8.1
ARG NODE_VERSION=22.17.1

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}
ENV no_proxy=${NO_PROXY}
ENV BUN_INSTALL=/root/.bun
ENV PATH=/root/.bun/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV ACP_RUNTIME_NAME=kimi
ENV ACP_COMMAND=kimi
ENV ACP_ARGS=acp
ENV KIMI_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir agent-client-protocol==0.10.1

RUN curl -fsSL https://bun.sh/install | bash \
    && bun --version \
    && bunx --version

RUN bun add -g @moonshot-ai/kimi-code

RUN python -c "import os, tarfile, urllib.request; \
version=os.environ.get('NODE_VERSION', '${NODE_VERSION}'); \
archive='/tmp/node.tar.xz'; \
url=f'https://nodejs.org/dist/v{version}/node-v{version}-linux-x64.tar.xz'; \
urllib.request.urlretrieve(url, archive); \
tarfile.open(archive, 'r:xz').extractall('/opt'); \
os.symlink(f'/opt/node-v{version}-linux-x64/bin/node', '/usr/local/bin/node'); \
os.symlink(f'/opt/node-v{version}-linux-x64/bin/npm', '/usr/local/bin/npm'); \
os.symlink(f'/opt/node-v{version}-linux-x64/bin/npx', '/usr/local/bin/npx')" \
    && node --version \
    && kimi --version

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

WORKDIR /workspace

CMD ["python", "/app/acp_runner.py"]
