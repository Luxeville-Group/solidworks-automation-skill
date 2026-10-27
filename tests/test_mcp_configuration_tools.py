"""SOLIDWORKS configuration-family MCP registration and input contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

import server  # noqa: E402
from scripts.validate_mcp import REQUIRED_TOOLS  # noqa: E402


CONFIGURATION_TOOLS = {
    "solidworks_inspect_configurations",
    "solidworks_create_configuration",
    "solidworks_activate_configuration",
}


def test_configuration_mcp_tools_are_registered() -> None:
    """@brief Register all three configuration entry points with MCP."""
    assert CONFIGURATION_TOOLS <= set(server.mcp._tool_manager._tools)


def test_release_mcp_gate_requires_configuration_tools() -> None:
    """@brief Release gates cover configuration entry points."""
    assert CONFIGURATION_TOOLS <= REQUIRED_TOOLS


def test_configuration_input_rejects_invalid_duplicate_policy() -> None:
    """@brief Configuration creation allows only idempotent reuse or strict failure."""
    with pytest.raises(ValueError):
        server.SolidWorksConfigurationCreateInput(
            configuration_name="İşleme",
            if_exists="overwrite",
        )


def test_configuration_input_rejects_negative_option_mask() -> None:
    """@brief Enum bitmasks cannot be negative."""
    with pytest.raises(ValueError):
        server.SolidWorksConfigurationCreateInput(
            configuration_name="İşleme",
            options=-1,
        )
