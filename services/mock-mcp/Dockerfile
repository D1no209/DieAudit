FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0
COPY services/mock-mcp/mock_mcp.py /app/mock_mcp.py
EXPOSE 8001
CMD ["python", "/app/mock_mcp.py"]
