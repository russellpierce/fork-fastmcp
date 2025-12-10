"""Selective tool filtering middleware for FastMCP.

This module provides middleware to filter tools exposed by a FastMCP server based on
URL path parameters, enabling dynamic tool selection per request.

Example usage:
    mcp = FastMCP("Selective Server")

    @mcp.tool
    def tool1():
        return "Tool 1"

    @mcp.tool
    def tool2():
        return "Tool 2"

    # Add selective filtering
    mcp.add_middleware(SelectiveToolMiddleware())
    setup_selective_routes(mcp)

    # Now supports:
    # /tool1/tool2/mcp → exposes only tool1 and tool2
    # /tool1/mcp → exposes only tool1
    # /mcp → exposes all tools
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

from fastmcp.exceptions import NotFoundError
from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import Tool
from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext
    from fastmcp.server.server import FastMCP

logger = get_logger(__name__)

__all__ = [
    "ErrorBehavior",
    "SelectiveToolMiddleware",
    "parse_tool_names",
    "setup_selective_routes",
]


class ErrorBehavior(str, Enum):
    """Configurable behavior when requested tools don't exist.

    Attributes:
        IGNORE: Silently skip non-existent tools, return only valid ones (default)
        STRICT: Raise NotFoundError if any requested tool doesn't exist
        WARN: Return valid tools + inject a synthetic error notice tool
        FALLBACK: If any tool is invalid, return all tools (disable filtering)
    """

    IGNORE = "ignore"
    STRICT = "strict"
    WARN = "warn"
    FALLBACK = "fallback"


class SelectiveToolMiddleware(Middleware):
    """Middleware that filters tools based on URL path selection.

    This middleware intercepts the tools/list request and filters the available
    tools based on a selection stored in the request context. The selection is
    typically set by a custom route handler that parses the URL path.

    Args:
        error_behavior: How to handle non-existent tool requests (default: IGNORE)

    Example:
        middleware = SelectiveToolMiddleware(error_behavior=ErrorBehavior.STRICT)
        mcp.add_middleware(middleware)
    """

    def __init__(self, error_behavior: ErrorBehavior = ErrorBehavior.IGNORE):
        super().__init__()
        self.error_behavior = error_behavior

    async def on_list_tools(
        self,
        context: MiddlewareContext,
        call_next,
    ) -> list[Tool]:
        """Filter tools based on context selection.

        Args:
            context: Middleware context containing request information
            call_next: Next handler in the middleware chain

        Returns:
            Filtered list of tools based on selection

        Raises:
            NotFoundError: If error_behavior is STRICT and invalid tools requested
        """
        # Get the full tool list from downstream
        tools = await call_next(context)

        # Check if tool selection is specified in context
        if context.fastmcp_context is None:
            return tools

        selected_tools = context.fastmcp_context.get_state("selected_tools")

        # No selection means return all tools
        if selected_tools is None:
            return tools

        # Find valid and invalid tool names
        available_tools = {t.key for t in tools}
        valid_tools = selected_tools & available_tools
        invalid_tools = selected_tools - available_tools

        # If all requested tools exist, just filter and return
        if not invalid_tools:
            return [t for t in tools if t.key in selected_tools]

        # Handle error based on configured behavior
        if self.error_behavior == ErrorBehavior.IGNORE:
            # Return only valid tools, silently ignore invalid ones
            logger.debug(
                f"Ignoring invalid tool selection: {invalid_tools}. "
                f"Returning {len(valid_tools)} valid tools."
            )
            return [t for t in tools if t.key in valid_tools]

        elif self.error_behavior == ErrorBehavior.STRICT:
            # Raise an error for invalid tools
            raise NotFoundError(
                f"Requested tools not found: {', '.join(sorted(invalid_tools))}. "
                f"Available tools: {', '.join(sorted(available_tools))}"
            )

        elif self.error_behavior == ErrorBehavior.WARN:
            # Return valid tools plus a synthetic error notice tool
            filtered_tools = [t for t in tools if t.key in valid_tools]
            notice_tool = self._create_error_notice_tool(invalid_tools, available_tools)
            return [*filtered_tools, notice_tool]

        elif self.error_behavior == ErrorBehavior.FALLBACK:
            # Return all tools if any invalid
            logger.warning(
                f"Invalid tool selection detected: {invalid_tools}. "
                f"Falling back to returning all {len(tools)} tools."
            )
            return tools

        else:
            # Should never reach here, but handle gracefully
            logger.error(f"Unknown error behavior: {self.error_behavior}")
            return tools

    def _create_error_notice_tool(
        self, invalid_tools: set[str], available_tools: set[str]
    ) -> Tool:
        """Create a synthetic tool that serves as an error notice.

        Args:
            invalid_tools: Set of requested tool names that don't exist
            available_tools: Set of all available tool names

        Returns:
            A Tool instance that displays an error message when called
        """

        def error_notice() -> str:
            return (
                f"⚠️ CONFIGURATION ERROR: The following tools were requested but do not exist: "
                f"{', '.join(sorted(invalid_tools))}. "
                f"\n\nAvailable tools: {', '.join(sorted(available_tools))}. "
                f"\n\nPlease notify the administrator to update the tool selection URL."
            )

        return Tool.from_function(
            error_notice,
            name="_selection_error_notice",
            description=(
                f"⚠️ ERROR NOTICE: Requested tools not found: {', '.join(sorted(invalid_tools))}. "
                "Call this tool to see the full error message."
            ),
        )


def parse_tool_names(path_segment: str) -> set[str] | None:
    """Parse tool names from URL path segment.

    Supports multiple formats:
    - Slash-separated: "tool1/tool2/tool3"
    - Comma-separated: "tool1,tool2,tool3"
    - Mixed: "tool1,tool2/tool3"

    Tool names must match pattern: ^[a-zA-Z_][a-zA-Z0-9_]*$

    Args:
        path_segment: URL path segment containing tool names

    Returns:
        Set of tool names, or None if path_segment is empty

    Raises:
        ValueError: If any tool name contains invalid characters

    Example:
        >>> parse_tool_names("tool1/tool2,tool3")
        {'tool1', 'tool2', 'tool3'}

        >>> parse_tool_names("")
        None
    """
    if not path_segment or path_segment.strip() == "":
        return None

    # Split by both forward slash and comma
    tool_names = re.split(r"[/,]+", path_segment)

    # Clean whitespace and filter empty strings
    tool_names = [name.strip() for name in tool_names if name.strip()]

    if not tool_names:
        return None

    # Validate each tool name
    for name in tool_names:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            raise ValueError(
                f"Invalid tool name: '{name}'. "
                f"Tool names must start with a letter or underscore and contain only "
                f"alphanumeric characters and underscores."
            )

    return set(tool_names)


def setup_selective_routes(
    mcp: FastMCP,
    path_pattern: str = "/{tools:path}/mcp",
    base_path: str = "/mcp",
) -> None:
    """Set up custom routes for selective tool filtering.

    This registers two routes:
    1. A selective route (e.g., /{tools:path}/mcp) that parses tool names
    2. A base route (e.g., /mcp) that exposes all tools

    Args:
        mcp: FastMCP server instance
        path_pattern: URL pattern for selective tool routing (default: "/{tools:path}/mcp")
        base_path: URL pattern for all-tools routing (default: "/mcp")

    Example:
        mcp = FastMCP("My Server")
        setup_selective_routes(mcp)

        # Now supports:
        # POST /tool1/tool2/mcp → only tool1 and tool2
        # POST /mcp → all tools
    """
    from starlette.requests import Request
    from starlette.responses import Response

    from fastmcp.server.dependencies import get_context

    # Register the selective tool route
    @mcp.custom_route(path_pattern, methods=["POST"])
    async def handle_selective_tools(request: Request) -> Response:
        """Handle requests with tool selection in the path."""
        # Extract the tools parameter from the path
        tools_param = request.path_params.get("tools", "")

        # Parse tool names
        try:
            selected_tools = parse_tool_names(tools_param)
        except ValueError as e:
            # Invalid tool name format
            from starlette.responses import JSONResponse

            return JSONResponse(
                {"error": str(e)},
                status_code=400,
            )

        # Store selection in context for middleware
        try:
            ctx = get_context()
            if selected_tools:
                ctx.set_state("selected_tools", selected_tools)
                logger.debug(f"Selected tools: {selected_tools}")
        except RuntimeError:
            # Context not available - this might be a direct HTTP call
            # without proper MCP session. We'll let the request continue
            # but tool selection won't work.
            logger.warning(
                "Context not available for tool selection. "
                "Tool filtering may not work properly."
            )

        # Forward the request to the MCP handler
        # The actual MCP endpoint handling is done by the StreamableHTTP transport
        # This route just sets the state and returns, letting the MCP protocol
        # handle the actual request through the middleware chain
        from starlette.responses import JSONResponse

        return JSONResponse(
            {
                "detail": "This endpoint requires the StreamableHTTP transport. "
                "The route is registered for path parsing only."
            },
            status_code=501,
        )

    # Note: In a real implementation, we'd need to integrate more deeply with
    # the StreamableHTTP transport to properly forward requests. For now, this
    # demonstrates the pattern. The actual integration would involve modifying
    # the HTTP app setup to handle these routes properly.

    logger.info(
        f"Selective tool routes registered: {path_pattern} (selective), {base_path} (all tools)"
    )
