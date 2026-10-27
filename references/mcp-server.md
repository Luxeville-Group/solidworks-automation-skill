# SolidWorks MCP Server Design

## Architecture

```text
Codex / Claude / other MCP clients
        ↓ stdio MCP
mcp-server/server.py
        ↓ Python COM / pywin32
SolidWorks Desktop
```

SolidWorks is a Windows desktop COM application, not a native MCP service. The MCP server exposes verified `scripts/sw_*.py` wrappers as controlled tools so agents need not generate large ad hoc scripts for every task.

## Transport choice

Default to `stdio`:

- Appropriate for local desktop software.
- The client launches the server as a subprocess with simple configuration.
- No network port is exposed, reducing the attack surface.

HTTP is not the default because:

- SolidWorks COM generally belongs to the current desktop user's session.
- Concurrent clients can corrupt active-document state.
- Remote access additionally needs authentication, Origin validation and desktop-session isolation.

## Multiclient registration

The installer invokes `mcp-server/register_all_ai_mcp.js` to register common local AI clients where possible:

- Codex: `codex mcp add solidworks -- <python> <server.py>`.
- Claude Code: `claude mcp add --scope user solidworks -- <python> <server.py>`.
- Claude Desktop: writes user-level `claude_desktop_config.json`.
- Cursor: writes global `~/.cursor/mcp.json`.
- Windsurf: writes global `~/.codeium/windsurf/mcp_config.json`.

Notes:

1. Local MCP configuration changes occur only when the `npx` installer or registration script is executed; importing a skill alone usually does not execute installation scripts.
2. Clients may need restarting or explicit trust confirmation before loading a new MCP server.
3. A cloud web product without access to local configuration cannot have a local MCP server installed by the skill alone.
4. JSON writes create `.bak-*` backups first; CLI clients remove and re-register an existing server of the same name.

## Concurrency

`mcp-server/server.py` uses a global `RLock` to serialize tools because:

- SolidWorks COM automation is not a general thread-safe service.
- Simultaneous document activation, selection and saving would interfere with shared state.
- Motion Study / Mate creation depends on the current selection set and must avoid concurrent contamination.

Each call attempts `pythoncom.CoInitialize()` so its MCP worker thread can use COM.

## Tool names

Prefixes express capability boundaries: `cadstudio_` for headless open formats, DFM, Routing, FEA and complex-geometry gates; `solidworks_` for actual SolidWorks COM operations.

CAD Studio gate tools:

- `cadstudio_resolve_backend`
- `cadstudio_write_open_format`
- `cadstudio_build_dxf_preview_scene`
- `cadstudio_check_dfm`
- `cadstudio_check_routing`
- `cadstudio_routing_preflight`
- `cadstudio_fea_preflight`
- `cadstudio_prepare_fea`
- `cadstudio_run_fea`
- `cadstudio_run_fea_convergence`
- `cadstudio_review_advanced_geometry`
- `cadstudio_create_ocp_loft`
- `cadstudio_create_ocp_surface`

Native SolidWorks tools:

- `solidworks_connect`
- `solidworks_new_document`
- `solidworks_open_document`
- `solidworks_inspect_configurations`
- `solidworks_create_configuration`
- `solidworks_activate_configuration`
- `solidworks_save_document`
- `solidworks_close_documents`
- `solidworks_export_active`
- `solidworks_review_active`
- `solidworks_add_rotary_motor`

## Safety boundaries

The first stage does not expose:

- Arbitrary Python execution.
- Arbitrary VBA macro execution.
- Direct file deletion.
- Hidden bulk closing or overwriting of user files.

Any new destructive tool must at least:

1. Include an explicit action such as `delete`, `overwrite` or `close_all` in its name.
2. Restrict paths and parameter ranges through the input schema.
3. Return structured results describing the actual affected scope.
4. Document `destructiveHint=True`.

## Suggested extension order

Prioritize high-value, low-ambiguity tools:

1. Documents/export: open, save, export, review.
2. Assemblies: add components, find by name, create concentric/coincident mates.
3. Motion Study: rotational/linear motors, calculation/playback.
4. Part modeling: controlled sketch and feature primitives.
5. Drawings: three views, BOM, PDF export.
6. Headless capabilities: DFM profiles, neutral Routing review, limited CalculiX linear/nonlinear analysis and mesh sequences, OCP ruled/smooth Loft, Sweep/Knit/Thicken and review of other complex-geometry plans.

Defer:

- Arbitrary sketch-constraint solving.
- Smooth lofts, complex sweeps, G1/G2/Class-A and mold-quality B-Rep generation beyond validated scope.
- Large contact problems, automatic penetration acceptance, collision and other advanced simulations or safety certification.

## Result format

Tools return JSON by default for subsequent LLM processing. `response_format="markdown"` is available for human reading.

Errors should include:

- `error_type`
- `message`
- `suggestion`

Do not expose raw Python tracebacks directly to MCP clients.
