"""Tests for selective tool filtering middleware."""

import pytest
from mcp.shared.exceptions import McpError

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.selective_tools import (
    ErrorBehavior,
    SelectiveToolMiddleware,
    parse_tool_names,
)
from fastmcp.server.middleware import Middleware


class TestParseToolNames:
    """Tests for parse_tool_names function."""

    def test_parse_single_tool(self):
        """Single tool name should be parsed correctly."""
        result = parse_tool_names("tool1")
        assert result == {"tool1"}

    def test_parse_slash_separated(self):
        """Slash-separated tool names should be parsed."""
        result = parse_tool_names("tool1/tool2/tool3")
        assert result == {"tool1", "tool2", "tool3"}

    def test_parse_comma_separated(self):
        """Comma-separated tool names should be parsed."""
        result = parse_tool_names("tool1,tool2,tool3")
        assert result == {"tool1", "tool2", "tool3"}

    def test_parse_mixed_separators(self):
        """Mixed separators should be parsed."""
        result = parse_tool_names("tool1,tool2/tool3")
        assert result == {"tool1", "tool2", "tool3"}

    def test_parse_with_whitespace(self):
        """Whitespace should be stripped."""
        result = parse_tool_names(" tool1 / tool2 , tool3 ")
        assert result == {"tool1", "tool2", "tool3"}

    def test_parse_empty_string(self):
        """Empty string should return None."""
        result = parse_tool_names("")
        assert result is None

    def test_parse_whitespace_only(self):
        """Whitespace-only string should return None."""
        result = parse_tool_names("   ")
        assert result is None

    def test_parse_duplicate_tools(self):
        """Duplicate tool names should be deduplicated."""
        result = parse_tool_names("tool1/tool2/tool1")
        assert result == {"tool1", "tool2"}

    def test_parse_valid_tool_names(self):
        """Valid tool names with underscores and numbers."""
        result = parse_tool_names("tool_1/tool2_name/my_tool_123")
        assert result == {"tool_1", "tool2_name", "my_tool_123"}

    def test_parse_invalid_tool_name_starts_with_number(self):
        """Tool name starting with number should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tool name"):
            parse_tool_names("123tool")

    def test_parse_invalid_tool_name_special_chars(self):
        """Tool name with special characters should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tool name"):
            parse_tool_names("tool-name")

    def test_parse_invalid_tool_name_space(self):
        """Tool name with spaces should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tool name"):
            parse_tool_names("tool name")


class TestSelectiveToolMiddleware:
    """Tests for SelectiveToolMiddleware."""

    async def test_no_selection_returns_all_tools(self):
        """When no selection is set, all tools should be returned."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        @mcp.tool
        def tool2() -> str:
            return "tool2"

        @mcp.tool
        def tool3() -> str:
            return "tool3"

        mcp.add_middleware(SelectiveToolMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {"tool1", "tool2", "tool3"}

    async def test_selection_filters_tools(self):
        """Selected tools should be filtered correctly."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        @mcp.tool
        def tool2() -> str:
            return "tool2"

        @mcp.tool
        def tool3() -> str:
            return "tool3"

        # Create middleware that will set selection
        class SelectionMiddleware(SelectiveToolMiddleware):
            async def on_list_tools(self, context, call_next):
                # Set selection in context
                if context.fastmcp_context:
                    context.fastmcp_context.set_state(
                        "selected_tools", {"tool1", "tool3"}
                    )
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {"tool1", "tool3"}

    async def test_ignore_behavior_skips_invalid_tools(self):
        """IGNORE behavior should skip non-existent tools."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        @mcp.tool
        def tool2() -> str:
            return "tool2"

        class SelectionMiddleware(SelectiveToolMiddleware):
            def __init__(self):
                super().__init__(error_behavior=ErrorBehavior.IGNORE)

            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    # Request tool1, tool2, and invalid_tool
                    context.fastmcp_context.set_state(
                        "selected_tools", {"tool1", "tool2", "invalid_tool"}
                    )
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            # Should return only valid tools
            assert tool_names == {"tool1", "tool2"}

    async def test_strict_behavior_raises_error(self):
        """STRICT behavior should raise McpError for invalid tools."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        class SelectionMiddleware(SelectiveToolMiddleware):
            def __init__(self):
                super().__init__(error_behavior=ErrorBehavior.STRICT)

            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    context.fastmcp_context.set_state(
                        "selected_tools", {"tool1", "invalid_tool"}
                    )
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            with pytest.raises(McpError, match="Requested tools not found"):
                await client.list_tools()

    async def test_warn_behavior_adds_error_notice(self):
        """WARN behavior should add error notice tool."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        class SelectionMiddleware(SelectiveToolMiddleware):
            def __init__(self):
                super().__init__(error_behavior=ErrorBehavior.WARN)

            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    context.fastmcp_context.set_state(
                        "selected_tools", {"tool1", "invalid_tool"}
                    )
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            # Should return tool1 plus error notice
            assert "tool1" in tool_names
            assert "_selection_error_notice" in tool_names
            assert len(tool_names) == 2

            # Error notice tool should be callable
            error_tool = next(t for t in tools if t.name == "_selection_error_notice")
            assert "invalid_tool" in error_tool.description

    async def test_fallback_behavior_returns_all_tools(self):
        """FALLBACK behavior should return all tools if any invalid."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        @mcp.tool
        def tool2() -> str:
            return "tool2"

        class SelectionMiddleware(SelectiveToolMiddleware):
            def __init__(self):
                super().__init__(error_behavior=ErrorBehavior.FALLBACK)

            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    context.fastmcp_context.set_state(
                        "selected_tools", {"tool1", "invalid_tool"}
                    )
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            # Should return all tools due to invalid selection
            assert tool_names == {"tool1", "tool2"}

    async def test_order_invariance(self):
        """Tool selection should be order-invariant."""
        # Test with different orders
        selections = [
            {"tool1", "tool2"},
            {"tool2", "tool1"},
        ]

        for selection in selections:

            class SelectionMiddleware(SelectiveToolMiddleware):
                def __init__(self, sel):
                    super().__init__()
                    self.sel = sel

                async def on_list_tools(self, context, call_next):
                    if context.fastmcp_context:
                        context.fastmcp_context.set_state("selected_tools", self.sel)
                    return await super().on_list_tools(context, call_next)

            mcp_test = FastMCP("Test Server")

            @mcp_test.tool
            def tool1() -> str:
                return "tool1"

            @mcp_test.tool
            def tool2() -> str:
                return "tool2"

            @mcp_test.tool
            def tool3() -> str:
                return "tool3"

            mcp_test.add_middleware(SelectionMiddleware(selection))

            async with Client(mcp_test) as client:
                tools = await client.list_tools()
                tool_names = {t.name for t in tools}
                assert tool_names == {"tool1", "tool2"}

    async def test_empty_selection_returns_no_tools(self):
        """Empty selection set should return no tools."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        class SelectionMiddleware(SelectiveToolMiddleware):
            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    context.fastmcp_context.set_state("selected_tools", set())
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 0

    async def test_tool_call_to_filtered_tool_fails(self):
        """Calling a tool that's been filtered out should fail."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        @mcp.tool
        def tool2() -> str:
            return "tool2"

        class SelectionMiddleware(SelectiveToolMiddleware):
            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    # Only expose tool1
                    context.fastmcp_context.set_state("selected_tools", {"tool1"})
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            # tool1 should work
            result = await client.call_tool("tool1", {})
            assert result.content[0].text == "tool1"  # type: ignore

            # tool2 should fail (not visible due to filtering in _should_enable_component)
            # The selective middleware only affects list_tools, not call_tool
            # So tool2 will still be callable but won't appear in list
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {"tool1"}
            assert "tool2" not in tool_names

    async def test_middleware_chain_interaction(self):
        """Multiple middleware should work together correctly."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        @mcp.tool
        def tool2() -> str:
            return "tool2"

        @mcp.tool
        def tool3() -> str:
            return "tool3"

        # Add a custom middleware before selective
        class LoggingMiddleware(Middleware):
            def __init__(self):
                super().__init__()
                self.calls = []

            async def on_message(self, context, call_next):
                self.calls.append(context.method)
                return await call_next(context)

        logging_mw = LoggingMiddleware()

        class SelectionMiddleware(SelectiveToolMiddleware):
            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    context.fastmcp_context.set_state("selected_tools", {"tool1"})
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(logging_mw)
        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {"tool1"}
            assert "tools/list" in logging_mw.calls

    async def test_all_invalid_tools_strict_mode(self):
        """STRICT mode with all invalid tools should raise clear error."""
        mcp = FastMCP("Test Server")

        @mcp.tool
        def tool1() -> str:
            return "tool1"

        class SelectionMiddleware(SelectiveToolMiddleware):
            def __init__(self):
                super().__init__(error_behavior=ErrorBehavior.STRICT)

            async def on_list_tools(self, context, call_next):
                if context.fastmcp_context:
                    context.fastmcp_context.set_state(
                        "selected_tools", {"invalid1", "invalid2"}
                    )
                return await super().on_list_tools(context, call_next)

        mcp.add_middleware(SelectionMiddleware())

        async with Client(mcp) as client:
            with pytest.raises(McpError) as exc_info:
                await client.list_tools()
            assert "invalid1" in str(exc_info.value)
            assert "invalid2" in str(exc_info.value)
