"""Sample code for FastMCP using SelectiveToolMiddleware."""

import asyncio

from fastmcp import FastMCP
from fastmcp.contrib.selective_tools import (
    ErrorBehavior,
    SelectiveToolMiddleware,
)

mcp = FastMCP("Selective Tools Example")

# Add selective tool middleware

mcp.add_middleware(SelectiveToolMiddleware(error_behavior=ErrorBehavior.IGNORE))


@mcp.tool
def echo(text: str) -> str:
    """Echo the input text"""
    return f"You said: {text}"


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b


@mcp.tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together"""
    return a * b


@mcp.resource("config://example")
def get_example_config() -> str:
    """Return an example configuration"""
    return """
    {
      "source": {
        "path": "server.py"
      },
      "deployment": {
        "transport": "http",
        "host": "127.0.0.1",
        "port": 8000,
        "path": "/mcp/"
      }
    }
    """


if __name__ == "__main__":
    asyncio.run(mcp.run_async())
