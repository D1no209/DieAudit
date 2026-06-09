FROM python:3.12-slim
RUN pip install --no-cache-dir httpx==0.28.1
COPY services/mock-agent/mock_agent.py /app/mock_agent.py
CMD ["python", "/app/mock_agent.py"]
