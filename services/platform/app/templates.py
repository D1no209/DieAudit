from pathlib import Path
from typing import Any

import yaml


class TemplateStore:
    def __init__(self, root: Path, folder: str) -> None:
        self.path = root / folder
        self.path.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        templates: list[dict[str, Any]] = []
        for file in sorted(self.path.glob("*.yaml")):
            data = self._read(file)
            data["_file"] = file.name
            templates.append(data)
        return templates

    def get(self, name: str) -> dict[str, Any]:
        file = self.path / f"{name}.yaml"
        if not file.exists():
            raise FileNotFoundError(f"template not found: {name}")
        return self._read(file)

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
