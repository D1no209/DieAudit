FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /usr/local/bin/

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1
ARG OPENCODE_VERSION=1.15.11
ARG OPENCODE_TARGET=linux-x64
ARG CODEBASE_MEMORY_MCP_VERSION=0.8.1

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}
ENV no_proxy=${NO_PROXY}
ENV PATH=/root/.opencode/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV OPENCODE_DISABLE_AUTOUPDATE=1

RUN uv pip install --system --no-cache agent-client-protocol==0.10.1

RUN python -c "import os, tarfile, urllib.request; \
version=os.environ.get('OPENCODE_VERSION', '${OPENCODE_VERSION}'); \
target=os.environ.get('OPENCODE_TARGET', '${OPENCODE_TARGET}'); \
url=f'https://github.com/anomalyco/opencode/releases/download/v{version}/opencode-{target}.tar.gz'; \
archive='/tmp/opencode.tar.gz'; \
urllib.request.urlretrieve(url, archive); \
tarfile.open(archive, 'r:gz').extract('opencode', '/usr/local/bin')" \
    && chmod 755 /usr/local/bin/opencode \
    && opencode --version

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

COPY services/agents/opencode-agent/opencode_acp_runner.py /app/opencode_acp_runner.py

WORKDIR /workspace

CMD ["python", "/app/opencode_acp_runner.py"]
