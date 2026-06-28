class GitClient:
    def clone(self, url: str, target: str, ref: str | None = None) -> dict:
        return {"url": url, "target": target, "ref": ref, "status": "not_executed"}
