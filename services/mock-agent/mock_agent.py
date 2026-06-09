import argparse
import json
import os
import time

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
        with httpx.Client(timeout=10) as client:
            health = client.get(f"{url}/health").json()
            tools = client.get(f"{url}/mcp/tools").json()
        result["mcp_results"][name] = {"health": health, "tools": tools}
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
