from typing import Any


FORBIDDEN_COMPOSE_KEYS = {"privileged", "pid", "ipc", "network_mode", "volumes"}


def validate_compose_service(service: dict[str, Any]) -> None:
    forbidden = sorted(FORBIDDEN_COMPOSE_KEYS.intersection(service))
    if forbidden:
        raise ValueError(f"compose service uses forbidden keys: {', '.join(forbidden)}")
