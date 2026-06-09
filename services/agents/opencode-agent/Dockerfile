FROM python:3.12-slim

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}
ENV no_proxy=${NO_PROXY}
ENV PATH=/root/.opencode/bin:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV OPENCODE_DISABLE_AUTOUPDATE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep tar \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir agent-client-protocol==0.10.1

RUN curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path \
    && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version

COPY services/agents/opencode-agent/opencode_acp_runner.py /app/opencode_acp_runner.py

WORKDIR /workspace

CMD ["python", "/app/opencode_acp_runner.py"]
