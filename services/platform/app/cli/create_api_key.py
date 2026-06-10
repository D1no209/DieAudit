from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.repositories import init_db
from app.services.auth import create_persisted_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a persisted DieAudit API key.")
    parser.add_argument("--name", default="bootstrap-admin", help="Display name for the API key.")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=[],
        help="Scope to grant. Repeat for multiple scopes, or pass comma-separated values.",
    )
    parser.add_argument("--metadata-json", default="{}", help="Optional metadata JSON stored with the key record.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    return parser.parse_args()


def expand_scopes(values: list[str]) -> list[str]:
    scopes: list[str] = []
    for value in values:
        scopes.extend(item.strip() for item in value.split(",") if item.strip())
    return scopes or ["admin"]


def parse_metadata(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid --metadata-json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("--metadata-json must decode to an object")
    return parsed


async def run() -> dict[str, Any]:
    args = parse_args()
    await init_db()
    result = await create_persisted_api_key(
        name=args.name,
        scopes=expand_scopes(args.scopes),
        metadata=parse_metadata(args.metadata_json),
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        record = result["record"]
        print("DieAudit API key created.")
        print(f"key_id: {record['key_id']}")
        print(f"name: {record['name']}")
        print(f"scopes: {', '.join(record['scopes'])}")
        print(f"api_key: {result['api_key']}")
        print("Store this key now; only its hash is persisted.")
    return result


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
