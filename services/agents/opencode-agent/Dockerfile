FROM python:3.12-slim-bookworm

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1
ARG OPENCODE_VERSION=1.15.11
ARG OPENCODE_TARGET=linux-x64

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}
ENV no_proxy=${NO_PROXY}
ENV PATH=/root/.opencode/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV OPENCODE_DISABLE_AUTOUPDATE=1

RUN pip install --no-cache-dir agent-client-protocol==0.10.1

RUN python -c "import os, tarfile, urllib.request; \
version=os.environ.get('OPENCODE_VERSION', '${OPENCODE_VERSION}'); \
target=os.environ.get('OPENCODE_TARGET', '${OPENCODE_TARGET}'); \
url=f'https://github.com/anomalyco/opencode/releases/download/v{version}/opencode-{target}.tar.gz'; \
archive='/tmp/opencode.tar.gz'; \
urllib.request.urlretrieve(url, archive); \
tarfile.open(archive, 'r:gz').extract('opencode', '/usr/local/bin')" \
    && chmod 755 /usr/local/bin/opencode \
    && opencode --version

COPY services/agents/opencode-agent/opencode_acp_runner.py /app/opencode_acp_runner.py

WORKDIR /workspace

CMD ["python", "/app/opencode_acp_runner.py"]
