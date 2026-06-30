FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /usr/local/bin/

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    no_proxy=${NO_PROXY}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ENV DOTNET_ROOT=/opt/dotnet \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    PATH="/root/.dotnet/tools:/opt/dotnet:${PATH}"

RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --fix-missing -o Acquire::Retries=5 --no-install-recommends bash ca-certificates curl default-jre-headless git libicu76 unzip wget \
    && mkdir -p /opt/cfr /opt/dotnet \
    && wget --tries=5 -q -O /opt/cfr/cfr.jar https://www.benf.org/other/cfr/cfr-0.152.jar \
    && printf '#!/bin/sh\nexec java -jar /opt/cfr/cfr.jar "$@"\n' > /usr/local/bin/cfr \
    && chmod +x /usr/local/bin/cfr \
    && curl --retry 5 --retry-delay 2 -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 8.0 --install-dir /opt/dotnet \
    && (dotnet tool install --global ilspycmd || true) \
    && rm -rf /var/lib/apt/lists/* /tmp/dotnet-install.sh

COPY services/platform/requirements.txt /app/requirements.txt
RUN uv pip install --system --no-cache -r /app/requirements.txt

COPY services/platform/app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
