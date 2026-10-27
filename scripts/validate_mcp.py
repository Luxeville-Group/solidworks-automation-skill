"""
Validate the SOLIDWORKS MCP Server protocol layer.

Do not invoke SOLIDWORKS COM tools. Start the local stdio server and check that tools/list contains essential tools, catching schema/registration errors before commits or in CI.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "mcp-server" / "server.py"

REQUIRED_TOOLS = {
    "solidworks_inspect_native_geometry",
    "solidworks_build_round_sweeps",
    "solidworks_import_step_part",
    "solidworks_replace_component_preserving_transform",
    "solidworks_exclude_reviewed_bodies",
    "cadstudio_read_artifact",
    "cadstudio_resolve_backend",
    "cadstudio_write_open_format",
    "cadstudio_build_dxf_preview_scene",
    "cadstudio_check_dfm",
    "cadstudio_check_routing",
    "cadstudio_routing_preflight",
    "solidworks_addin_host_status",
    "cadstudio_fea_preflight",
    "cadstudio_prepare_fea",
    "cadstudio_run_fea",
    "cadstudio_run_fea_convergence",
    "cadstudio_review_advanced_geometry",
    "cadstudio_create_ocp_loft",
    "cadstudio_create_ocp_surface",
    "solidworks_health_check",
    "solidworks_recover",
    "solidworks_connect",
    "solidworks_new_document",
    "solidworks_create_basic_part",
    "solidworks_open_document",
    # Modeling tools: actual part-modeling entry points require regression coverage.
    "solidworks_sketch_and_extrude",
    "solidworks_revolve",
    "solidworks_fillet",
    "solidworks_chamfer",
    "solidworks_shell",
    "solidworks_pattern",
    "solidworks_mirror_feature",
    "solidworks_list_edges",
    # Geometry checks: mechanical design needs measured dimension and mass readback.
    "solidworks_mass_properties",
    "solidworks_bounding_box",
    "solidworks_interference_check",
    "solidworks_document_units",
    # Specification-driven modeling: versionable, idempotent, and self-validating.
    "design_spec_validate",
    "design_spec_build",
    "solidworks_add_component",
    "solidworks_set_component_fixed",
    "solidworks_save_document",
    "solidworks_close_documents",
    "solidworks_add_coincident_mate",
    "solidworks_add_distance_mate",
    "solidworks_add_concentric_mate",
    "solidworks_set_appearance",
    "solidworks_export_active",
    "solidworks_inspect_configurations",
    "solidworks_create_configuration",
    "solidworks_activate_configuration",
    "solidworks_update_dimension",
    "solidworks_set_custom_properties",
    "solidworks_batch_export_files",
    "solidworks_export_assembly_bom",
    "solidworks_pack_and_go",
    "solidworks_review_active",
    "solidworks_create_hole_feature",
    "solidworks_inspect_hole_features",
    "solidworks_add_rotary_motor",
    "solidworks_inspect_motion_studies",
    "solidworks_validate_motion_study",
    "solidworks_generate_drawing",
    "solidworks_review_drawing",
    "solidworks_inspect_drawing",
}


def _configure_stdio_utf8() -> None:
    """Prefer UTF-8 diagnostics on Windows systems with legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


async def _list_tools() -> set[str]:
    """Start the MCP server and read its tool list."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        cwd=str(ROOT),
    )
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return {tool.name for tool in result.tools}


async def _main() -> int:
    """Check the MCP tool inventory."""
    if not SERVER_PATH.exists():
        raise FileNotFoundError(f"MCP Server bulunamadı: {SERVER_PATH}")
    tool_names = await _list_tools()
    missing = sorted(REQUIRED_TOOLS - tool_names)
    if missing:
        raise AssertionError("Eksik MCP araçları: " + ", ".join(missing))
    print(f"MCP doğrulaması başarılı: {len(tool_names)} araç görünür.")
    return 0


if __name__ == "__main__":
    _configure_stdio_utf8()
    try:
        raise SystemExit(asyncio.run(_main()))
    except Exception as exc:
        print(f"MCP doğrulaması başarısız: {exc}", file=sys.stderr)
        raise SystemExit(1)
