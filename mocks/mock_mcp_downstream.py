from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock downstream MCP server")

TOOLS = [
    {
        "name": "lookup_status",
        "description": "Read-only demo tool",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "admin_reset_key",
        "description": "Admin demo tool",
        "inputSchema": {"type": "object"},
    },
]


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    payload = await request.json()
    if payload.get("method") == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": payload.get("id"), "result": {"tools": TOOLS}})
    if payload.get("method") == "tools/call":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"called {payload.get('params', {}).get('name')}",
                        }
                    ]
                },
            }
        )
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "error": {"code": -32601, "message": "Method not found"},
        }
    )
