"""A complete, runnable example for FastMCP's SelectiveToolMiddleware.

This script demonstrates how to use URL-based selective tool filtering by
combining two custom ASGI middlewares.
"""

import re
import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send

from fastmcp import FastMCP
from fastmcp.contrib.selective_tools import (
    ErrorBehavior,
    SelectiveToolMiddleware,
    parse_tool_names,
)
from fastmcp.server.dependencies import get_context

# --- Middleware Definitions ---

class URLRewriterMiddleware:
    """Rewrites URL paths and passes tool selections in the ASGI scope."""
    def __init__(self, app: ASGIApp):
        self.app = app
        self.path_regex = re.compile(r"^/(?P<tools>[^/]+)/mcp$")

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            match = self.path_regex.match(path)
            if match:
                tools_param = match.group("tools")
                selected = parse_tool_names(tools_param)

                if "state" not in scope:
                    scope["state"] = {}
                scope["state"]["selected_tools"] = selected

                scope["path"] = "/mcp"

        await self.app(scope, receive, send)

class ContextPopulaterMiddleware:
    """Reads tool selections from ASGI scope and sets them in the MCP context."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            selected = scope.get("state", {}).get("selected_tools")
            if selected:
                ctx = get_context()
                ctx.set_state("selected_tools", selected)

        await self.app(scope, receive, send)

# --- App Factory ---

def create_app():
    """Creates and configures a new FastMCP ASGI app instance."""
    mcp = FastMCP("Selective Tools Example")

    @mcp.tool
    def echo(text: str) -> str:
        """Echo the input text"""
        return f"You said: {text}"

    @mcp.tool
    def add(a: int, b: int) -> int:
        """Add two numbers together"""
        # The return type must match the annotation for correct JSON serialization
        return a + b

    @mcp.tool
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers together"""
        # The return type must match the annotation
        return a * b

    mcp.add_middleware(ContextPopulaterMiddleware)
    mcp.add_middleware(SelectiveToolMiddleware(error_behavior=ErrorBehavior.IGNORE))

    app = mcp.http_app(transport="http", json_response=True)
    return URLRewriterMiddleware(app)

# --- Main Execution ---

if __name__ == "__main__":
    app = create_app()
    print("Starting server on http://127.0.0.1:8000")
    print("Try sending requests to:")
    print("  - http://127.0.0.1:8000/mcp (all tools)")
    print("  - http://127.0.0.1:8000/echo/mcp (only echo tool)")
    print("  - http://127.0.0.1:8000/add,multiply/mcp (add and multiply tools)")

    uvicorn.run(app, host="127.0.0.1", port=8000)
