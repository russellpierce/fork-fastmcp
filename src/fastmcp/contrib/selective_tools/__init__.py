"""Selective tool filtering for FastMCP.

This module provides middleware to dynamically filter tools based on URL path
parameters, enabling fine-grained control over which tools are exposed to
different clients or API endpoints.

Example:
    from fastmcp import FastMCP
    from fastmcp.contrib.selective_tools import (
        SelectiveToolMiddleware,
        ErrorBehavior,
        parse_tool_names,
    )

    mcp = FastMCP("My Server")

    @mcp.tool
    def tool1():
        return "Tool 1"

    @mcp.tool
    def tool2():
        return "Tool 2"

    # Add selective filtering middleware
    mcp.add_middleware(
        SelectiveToolMiddleware(error_behavior=ErrorBehavior.IGNORE)
    )
"""

from fastmcp.contrib.selective_tools.selective_tools import (
    ErrorBehavior,
    SelectiveToolMiddleware,
    parse_tool_names,
    setup_selective_routes,
)

__all__ = [
    "ErrorBehavior",
    "SelectiveToolMiddleware",
    "parse_tool_names",
    "setup_selective_routes",
]
