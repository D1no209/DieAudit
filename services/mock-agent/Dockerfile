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
RUN uv pip install --system --no-cache httpx==0.28.1
COPY services/mock-agent/mock_agent.py /app/mock_agent.py
CMD ["python", "/app/mock_agent.py"]
