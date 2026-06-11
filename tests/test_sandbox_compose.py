import pytest
from fastapi import HTTPException

from app.api.routes import _sandbox_compose_to_service_request
from app.schemas import StartSandboxComposeRequest


def test_sandbox_compose_single_service_maps_to_sandbox_service_request() -> None:
    request = StartSandboxComposeRequest(
        compose_yaml="""
services:
  target:
    image: python:3.12-slim
    command: python -m http.server 8080
    environment:
      APP_ENV: test
    ports:
      - "8080:8080"
    x-dieaudit:
      healthcheck_path: /
""".strip()
    )

    service = _sandbox_compose_to_service_request(request)

    assert service.image == "python:3.12-slim"
    assert service.command == ["sh", "-lc", "python -m http.server 8080"]
    assert service.env == {"APP_ENV": "test"}
    assert service.service_name == "target"
    assert service.port == 8080
    assert service.healthcheck_path == "/"


def test_sandbox_compose_rejects_multi_service_stack() -> None:
    request = StartSandboxComposeRequest(
        compose_yaml="""
services:
  web:
    image: nginx
    command: nginx -g 'daemon off;'
  db:
    image: postgres
    command: postgres
""".strip(),
        service_name="web",
    )

    with pytest.raises(HTTPException, match="multi-service"):
        _sandbox_compose_to_service_request(request)


def test_sandbox_compose_rejects_docker_socket_mount() -> None:
    request = StartSandboxComposeRequest(
        compose_yaml="""
services:
  target:
    image: alpine
    command: sleep 60
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
""".strip()
    )

    with pytest.raises(HTTPException, match="Docker socket"):
        _sandbox_compose_to_service_request(request)
