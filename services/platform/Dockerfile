FROM python:3.12-slim

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
    PATH="/root/.dotnet/tools:/opt/dotnet:${PATH}" \
    DOTNET_CLI_TELEMETRY_OPTOUT=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl default-jre-headless git libicu72 unzip wget \
    && (apt-get install -y --no-install-recommends jadx || printf '#!/bin/sh\necho "jadx is not installed in this image" >&2\nexit 127\n' > /usr/local/bin/jadx) \
    && chmod +x /usr/local/bin/jadx \
    && mkdir -p /opt/cfr /opt/dotnet \
    && wget -q -O /opt/cfr/cfr.jar https://www.benf.org/other/cfr/cfr-0.152.jar \
    && printf '#!/bin/sh\nexec java -jar /opt/cfr/cfr.jar "$@"\n' > /usr/local/bin/cfr \
    && chmod +x /usr/local/bin/cfr \
    && curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 8.0 --install-dir /opt/dotnet \
    && (dotnet tool install --global ilspycmd || printf '#!/bin/sh\necho "ilspycmd is not installed in this image" >&2\nexit 127\n' > /usr/local/bin/ilspycmd) \
    && chmod +x /usr/local/bin/ilspycmd \
    && rm -rf /var/lib/apt/lists/* /tmp/dotnet-install.sh

COPY services/platform/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/platform/app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
