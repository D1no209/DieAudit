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
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0
COPY services/mock-mcp/mock_mcp.py /app/mock_mcp.py
EXPOSE 8001
CMD ["python", "/app/mock_mcp.py"]
