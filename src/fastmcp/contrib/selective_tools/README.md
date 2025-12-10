# Selective Tool Filtering

Middleware for FastMCP that enables dynamic tool filtering based on URL path parameters. This allows a single server instance to expose different subsets of tools to different clients or API endpoints.

## Use Cases

- **Multi-tenant APIs**: Expose different tool sets to different customers
- **Permission-based access**: Restrict tools based on authentication context
- **API versioning**: Gradually expose new tools without breaking existing clients
- **Development/Production separation**: Different tool sets for different environments
- **Client-specific features**: Custom tool combinations per integration

## Installation

This module is included in FastMCP under `fastmcp.contrib.selective_tools`.

## Quick Start

```python
from fastmcp import FastMCP
from fastmcp.contrib.selective_tools import (
    SelectiveToolMiddleware,
    ErrorBehavior,
)

# Create server
mcp = FastMCP("My Server")

# Add tools
@mcp.tool
def echo(text: str) -> str:
    """Echo text back to user."""
    return f"You said: {text}"

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

# Add selective filtering middleware
mcp.add_middleware(
    SelectiveToolMiddleware(error_behavior=ErrorBehavior.IGNORE)
)
```

## Tool Selection

The middleware reads tool selection from the request context state. Tools are specified using the `"selected_tools"` state key:

```python
from fastmcp.server.dependencies import get_context

# In a custom route handler or middleware
ctx = get_context()
ctx.set_state("selected_tools", {"echo", "add"})
```

When `selected_tools` is set:
- Only tools with names in the set are exposed
- Other tools are filtered out from `tools/list` responses
- Tool calls to filtered tools will fail with `NotFoundError`

When `selected_tools` is `None` or not set:
- All tools are exposed (normal behavior)

## Error Behaviors

Configure how the middleware handles requests for non-existent tools:

### IGNORE (Default)

Silently skip non-existent tools, return only valid ones. Best for flexible discovery scenarios.

```python
SelectiveToolMiddleware(error_behavior=ErrorBehavior.IGNORE)

# Request: selected_tools={"echo", "invalid_tool"}
# Result: Returns only "echo" tool
```

### STRICT

Raise `NotFoundError` if any requested tool doesn't exist. Best for API contract enforcement.

```python
SelectiveToolMiddleware(error_behavior=ErrorBehavior.STRICT)

# Request: selected_tools={"echo", "invalid_tool"}
# Result: Raises NotFoundError with details
```

### WARN

Return valid tools plus inject a synthetic error notice tool. Best for informing clients of misconfiguration.

```python
SelectiveToolMiddleware(error_behavior=ErrorBehavior.WARN)

# Request: selected_tools={"echo", "invalid_tool"}
# Result: Returns "echo" + "_selection_error_notice" tool
```

The error notice tool contains detailed information about which tools were not found.

### FALLBACK

If any tool is invalid, return all tools (disable filtering). Best for graceful degradation.

```python
SelectiveToolMiddleware(error_behavior=ErrorBehavior.FALLBACK)

# Request: selected_tools={"echo", "invalid_tool"}
# Result: Returns all tools (echo, add, multiply)
```

## URL-Based Selection

While the middleware operates on context state, you can integrate it with URL routing. The module provides a helper for parsing tool names from paths:

```python
from fastmcp.contrib.selective_tools import parse_tool_names

# Parse from URL paths
tools = parse_tool_names("echo/add")  # {"echo", "add"}
tools = parse_tool_names("echo,add")  # {"echo", "add"} (comma-separated)
tools = parse_tool_names("echo")      # {"echo"}
tools = parse_tool_names("")          # None (no filtering)
```

### Custom Route Integration

```python
from starlette.requests import Request
from starlette.responses import Response
from fastmcp.server.dependencies import get_context
from fastmcp.contrib.selective_tools import parse_tool_names

@mcp.custom_route("/{tools:path}/mcp", methods=["POST"])
async def selective_endpoint(request: Request) -> Response:
    """Handle selective tool requests."""
    # Extract tool names from path
    tools_param = request.path_params.get("tools", "")
    selected = parse_tool_names(tools_param)

    # Store in context
    ctx = get_context()
    if selected:
        ctx.set_state("selected_tools", selected)

    # Forward to MCP handler
    # (Implementation depends on transport layer)
```

## Complete Example

See `example.py` for a complete working example with three tools and selective filtering.

Run the example:

```bash
python -m fastmcp.contrib.selective_tools.example
```

## API Reference

### `SelectiveToolMiddleware`

Middleware class that filters tools based on context selection.

**Constructor:**
- `error_behavior` (ErrorBehavior, optional): How to handle non-existent tools. Default: `ErrorBehavior.IGNORE`

**Methods:**
- `on_list_tools(context, call_next)`: Filters tool list based on context state

### `ErrorBehavior`

Enum defining error handling strategies.

**Values:**
- `IGNORE`: Skip non-existent tools
- `STRICT`: Raise error for non-existent tools
- `WARN`: Add error notice tool
- `FALLBACK`: Return all tools if any invalid

### `parse_tool_names(path_segment: str) -> set[str] | None`

Parse tool names from URL path segment.

**Args:**
- `path_segment`: String containing tool names (slash or comma separated)

**Returns:**
- Set of tool names, or None if empty

**Raises:**
- `ValueError`: If tool names contain invalid characters

**Valid tool name pattern:** `^[a-zA-Z_][a-zA-Z0-9_]*$`

## Testing

The middleware includes comprehensive tests covering:
- All error behaviors
- Path parsing (slash, comma, mixed)
- Valid/invalid tool selection
- Edge cases (empty selection, duplicates)
- Order invariance

Run tests:

```bash
pytest tests/contrib/test_selective_tools.py
```

## Limitations

- Tool selection is request-scoped (not persistent)
- Requires integration with HTTP transport for URL-based routing
- Error notice tool (WARN mode) appears in tool list but isn't a real tool
- STRICT mode returns HTTP errors which may not be ideal for all clients

## Advanced Usage

### Per-Request Selection

```python
# In middleware or custom handler
async def on_request(context, call_next):
    # Determine tools based on authentication, headers, etc.
    user_role = get_user_role(context)

    if user_role == "admin":
        # Admins get all tools (don't set selected_tools)
        pass
    elif user_role == "user":
        # Regular users get limited tools
        context.fastmcp_context.set_state(
            "selected_tools",
            {"echo", "add"}
        )

    return await call_next(context)
```

### Dynamic Tool Groups

```python
TOOL_GROUPS = {
    "basic": {"echo", "add"},
    "advanced": {"multiply", "divide", "power"},
    "all": {"echo", "add", "multiply", "divide", "power"},
}

# Select by group name
ctx.set_state("selected_tools", TOOL_GROUPS["basic"])
```

### Combining with Authentication

```python
from fastmcp.server.auth import JWTVerifier

# Define tools with tags
@mcp.tool(tags={"public"})
def echo(text: str) -> str:
    return text

@mcp.tool(tags={"admin"})
def delete_data(id: str) -> str:
    return f"Deleted {id}"

# Filter based on JWT claims
def filter_tools_by_auth(jwt_claims):
    if "admin" in jwt_claims.get("roles", []):
        return None  # All tools
    else:
        return {"echo"}  # Only public tools
```

## Contributing

This module is part of FastMCP's contrib package. Contributions welcome!

## License

Same as FastMCP
