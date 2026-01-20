"""
MCP Integration Tests

Tests for verifying MCP client infrastructure and tool integration.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestMCPConfig:
    """Tests for MCP configuration."""

    def test_mcp_config_from_env(self):
        """Test loading MCP config from environment variables."""
        from app.mcp.config import load_config_from_env, MCPConfig

        # Set test environment
        with patch.dict(os.environ, {
            'MCP_ENABLED': 'true',
            'MCP_STORAGE_URL': 'http://test-storage:8000',
            'MCP_CONNECTION_TIMEOUT': '60',
        }):
            config = load_config_from_env()

            assert config.enabled is True
            assert config.connection_timeout == 60

            # Should have storage server configured
            storage_server = config.get_server('storage')
            if storage_server:
                assert 'test-storage' in storage_server.url

    def test_server_tenant_access(self):
        """Test tenant access control on servers."""
        from app.mcp.config import MCPServerConfig

        # Server with whitelist
        server = MCPServerConfig(
            name="test",
            url="http://test:8000",
            tenant_whitelist=["tenant-1", "tenant-2"],
        )

        assert server.is_accessible_by_tenant("tenant-1") is True
        assert server.is_accessible_by_tenant("tenant-3") is False

        # Server with blacklist
        server2 = MCPServerConfig(
            name="test2",
            url="http://test:8000",
            tenant_blacklist=["tenant-bad"],
        )

        assert server2.is_accessible_by_tenant("tenant-1") is True
        assert server2.is_accessible_by_tenant("tenant-bad") is False

    def test_tool_prefix(self):
        """Test tool name prefixing."""
        from app.mcp.config import MCPServerConfig

        server = MCPServerConfig(
            name="storage",
            url="http://test:8000",
            tool_prefix="storage_",
        )

        assert server.get_tool_name("upload") == "storage_upload"
        assert server.get_tool_name("download") == "storage_download"


class TestMCPToolAdapter:
    """Tests for MCP tool adapter."""

    def test_json_schema_to_parameters(self):
        """Test converting JSON Schema to tool parameters."""
        from app.mcp.tool_adapter import input_schema_to_parameters

        schema = {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 100
                }
            },
            "required": ["filename", "tenant_id"]
        }

        params = input_schema_to_parameters(schema)

        assert len(params) == 3

        # Check required params
        filename_param = next(p for p in params if p.name == "filename")
        assert filename_param.required is True
        assert filename_param.type.value == "string"

        # Check optional param
        limit_param = next(p for p in params if p.name == "limit")
        assert limit_param.required is False
        assert limit_param.default == 100

    def test_create_dynamic_params_model(self):
        """Test creating dynamic Pydantic models for tool params."""
        from app.mcp.tool_adapter import create_dynamic_params_model

        schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": ["query"]
        }

        ParamsModel = create_dynamic_params_model("test_tool", schema)

        # Should be able to instantiate with required param
        params = ParamsModel(query="test search")
        assert params.query == "test search"
        assert params.limit == 10  # default


class TestMCPQwenIntegration:
    """Tests for Qwen-Agent integration."""

    def test_json_schema_to_qwen_params(self):
        """Test converting to Qwen-Agent parameter format."""
        from app.mcp.qwen_integration import _json_schema_to_qwen_params

        schema = {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "File content"
                },
                "filename": {
                    "type": "string",
                    "description": "Filename"
                }
            },
            "required": ["content"]
        }

        params = _json_schema_to_qwen_params(schema)

        assert len(params) == 2

        content_param = next(p for p in params if p['name'] == 'content')
        assert content_param['required'] is True
        assert content_param['type'] == 'string'

        filename_param = next(p for p in params if p['name'] == 'filename')
        assert filename_param['required'] is False


class TestMCPClientManager:
    """Tests for MCP client manager."""

    @pytest.mark.asyncio
    async def test_manager_initialization(self):
        """Test manager initialization."""
        from app.mcp.client_manager import MCPClientManager
        from app.mcp.config import MCPConfig

        config = MCPConfig(enabled=True, servers=[])
        manager = MCPClientManager(config)

        assert manager._initialized is False

        # Initialize (no servers to connect)
        await manager.initialize()

        assert manager._initialized is True

        # Cleanup
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_get_tools_empty(self):
        """Test getting tools when no servers configured."""
        from app.mcp.client_manager import MCPClientManager
        from app.mcp.config import MCPConfig

        config = MCPConfig(enabled=True, servers=[])
        manager = MCPClientManager(config)
        await manager.initialize()

        tools = await manager.get_tools_for_tenant("test-tenant")
        assert len(tools) == 0

        await manager.shutdown()

    def test_server_status_empty(self):
        """Test server status with no connections."""
        from app.mcp.client_manager import MCPClientManager
        from app.mcp.config import MCPConfig

        config = MCPConfig(enabled=True, servers=[])
        manager = MCPClientManager(config)

        status = manager.get_server_status()
        assert status == {}


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
