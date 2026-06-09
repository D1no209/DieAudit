from fastapi import FastAPI
import uvicorn

app = FastAPI(title="DieAudit Mock MCP")


@app.get("/health")
async def health():
    return {"ok": True, "service": "mock-mcp"}


@app.get("/mcp/tools")
async def tools():
    return {
        "tools": [
            {"name": "filesystem.read", "description": "Read files from the mounted read-only workspace."},
            {"name": "code.search", "description": "Search code snippets in the mounted workspace."},
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
