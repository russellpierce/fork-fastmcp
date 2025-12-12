import uuid
import pytest
from async_asgi_testclient import TestClient

# Import the app factory from the refactored example file.
from fastmcp.contrib.selective_tools.example import create_app

# Mark all tests in this file as integration tests.
pytestmark = pytest.mark.integration

# Define the required headers for MCP JSON requests
JSON_HEADERS = {
    "Content-Type": "application/mcp+json",
    "Accept": "application/json",
}

def mcp_tool_call(tool_name: str, **kwargs):
    """Helper function to create a valid MCP tool call message."""
    return {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": str(uuid.uuid4()),
                "name": tool_name,
                "input": kwargs,
            }
        ],
    }

@pytest.mark.asyncio
async def test_all_tools_enabled():
    """Verify that all tools are enabled on the default /mcp endpoint."""
    app = create_app()
    async with TestClient(app) as client:
        # Test echo tool
        response_echo = await client.post(
            "/mcp",
            json=mcp_tool_call("echo", text="hello"),
            headers=JSON_HEADERS,
        )
        assert response_echo.status_code == 200
        response_json = response_echo.json()
        assert response_json["role"] == "tool"
        assert response_json["content"][0]["type"] == "tool_result"
        assert response_json["content"][0]["content"] == "You said: hello"

        # Test add tool
        response_add = await client.post(
            "/mcp",
            json=mcp_tool_call("add", a=1, b=2),
            headers=JSON_HEADERS,
        )
        assert response_add.status_code == 200
        assert response_add.json()["content"][0]["content"] == 3

@pytest.mark.asyncio
async def test_single_tool_enabled():
    """Verify that only the 'echo' tool is enabled on the /echo/mcp endpoint."""
    app = create_app()
    async with TestClient(app) as client:
        # Test echo tool (should succeed)
        response_echo = await client.post(
            "/echo/mcp",
            json=mcp_tool_call("echo", text="hello"),
            headers=JSON_HEADERS,
        )
        assert response_echo.status_code == 200
        assert "You said: hello" in response_echo.json()["content"][0]["content"]

        # Test add tool (should fail with a tool not found error)
        response_add = await client.post(
            "/echo/mcp",
            json=mcp_tool_call("add", a=1, b=2),
            headers=JSON_HEADERS,
        )
        assert response_add.status_code == 400
        assert "No tool named 'add' available" in response_add.text

@pytest.mark.asyncio
async def test_multiple_tools_enabled():
    """Verify that 'add' and 'multiply' are enabled on the /add,multiply/mcp endpoint."""
    app = create_app()
    async with TestClient(app) as client:
        # Test add tool (should succeed)
        response_add = await client.post(
            "/add,multiply/mcp",
            json=mcp_tool_call("add", a=2, b=3),
            headers=JSON_HEADERS,
        )
        assert response_add.status_code == 200
        assert response_add.json()["content"][0]["content"] == 5

        # Test multiply tool (should succeed)
        response_multiply = await client.post(
            "/add,multiply/mcp",
            json=mcp_tool_call("multiply", a=2, b=3),
            headers=JSON_HEADERS,
        )
        assert response_multiply.status_code == 200
        assert response_multiply.json()["content"][0]["content"] == 6

        # Test echo tool (should fail with a tool not found error)
        response_echo = await client.post(
            "/add,multiply/mcp",
            json=mcp_tool_call("echo", text="hello"),
            headers=JSON_HEADERS,
        )
        assert response_echo.status_code == 400
        assert "No tool named 'echo' available" in response_echo.text
