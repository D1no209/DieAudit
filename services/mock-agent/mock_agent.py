import argparse
import json
import os
import time
from urllib.parse import urlsplit, urlunsplit

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idle", action="store_true")
    args = parser.parse_args()
    if args.idle:
        while True:
            time.sleep(3600)

    servers = json.loads(os.environ.get("MCP_SERVERS_JSON", "{}"))
    payload = json.loads(os.environ.get("AGENT_INPUT_JSON", "{}"))
    result = {
        "agent_run_id": os.environ.get("AGENT_RUN_ID"),
        "audit_run_id": os.environ.get("AUDIT_RUN_ID"),
        "project_id": os.environ.get("PROJECT_ID"),
        "input": payload,
        "mcp_results": {},
    }
    for name, server in servers.items():
        url = server["url"].rstrip("/")
        service_root = _service_root(url)
        with httpx.Client(timeout=10) as client:
            health = _get_json(client, f"{service_root}/health")
            tools = _first_json(
                client,
                [
                    f"{url}/tools",
                    f"{service_root}/mcp/tools",
                    f"{service_root}/tools",
                ],
            ) or {"available": False, "reason": "tools endpoint not advertised"}
        result["mcp_results"][name] = {"health": health, "tools": tools}
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


def _service_root(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _get_json(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def _first_json(client: httpx.Client, urls: list[str]) -> dict | None:
    for url in urls:
        response = client.get(url)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        return response.json()
    return None


if __name__ == "__main__":
    main()
