from pathlib import Path
from typing import Any

import yaml


class TemplateStore:
    def __init__(self, root: Path, folder: str, *, include_demo: bool = False) -> None:
        self.path = root / folder
        self.include_demo = include_demo
        self.path.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        templates: list[dict[str, Any]] = []
        for file in sorted(self.path.glob("*.yaml")):
            data = self._read(file)
            if not self.include_demo and self.is_demo_template(data):
                continue
            data["_file"] = file.name
            templates.append(data)
        return templates

    def get(self, name: str) -> dict[str, Any]:
        file = self.path / f"{name}.yaml"
        if not file.exists():
            raise FileNotFoundError(f"template not found: {name}")
        data = self._read(file)
        if not self.include_demo and self.is_demo_template(data):
            raise FileNotFoundError(f"template not enabled: {name}")
        return data

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ValueError("template requires a string name")
        file = self.path / f"{name}.yaml"
        file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return data

    @staticmethod
    def _read(file: Path) -> dict[str, Any]:
        with file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"invalid template: {file}")
        return data

    @staticmethod
    def is_demo_template(data: dict[str, Any]) -> bool:
        if data.get("profile") == "demo" or data.get("demo") is True:
            return True
        image = str(data.get("image") or "")
        if "mock-agent" in image or "mock-mcp" in image:
            return True
        protocol = data.get("protocol") or {}
        if isinstance(protocol, dict) and protocol.get("runtime") == "mock":
            return True
        return False
