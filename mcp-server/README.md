# SOLIDWORKS MCP Server

This local MCP server exposes CAD-free open-format tools and allowlisted SOLIDWORKS COM tools. MCP, CAD Studio, the skill, and CLI share capability definitions and data contracts.

SOLIDWORKS is a Windows desktop COM application. The server defaults to `stdio` and serializes operations with a global lock. Use one client. `--transport streamable-http` exposes the same tools to a remote client, such as a Linux agent connecting to a Windows CAD host; the lock still applies.

## Requirements and startup

- Windows 10/11 and Python 3.10+.
- Native operations target SOLIDWORKS 2026. Launch it at least once after installation to complete COM registration.
- `cadstudio_write_open_format` does not require SOLIDWORKS/AutoCAD.

Install dependencies from the repository root:

```powershell
pip install -r mcp-server\requirements.txt
```

Start the server:

```powershell
python mcp-server\server.py
```

The MCP client normally launches this subprocess. Python-based MCP execution does not require Node.js. The Codex-only PowerShell registrar below runs without Node.js; the multi-client PowerShell wrapper invokes JavaScript and requires Node.js.

## HTTP transport

Use HTTP when a remote client cannot start a stdio subprocess on the CAD host:

```powershell
python -m pip install uvicorn
$env:SW_MCP_TOKEN = "<replace-with-random-shared-secret>"
python mcp-server\server.py --transport streamable-http --host 0.0.0.0 --port 8000 `
  --allow-host "192.168.1.10:*" --output-root "C:\cad-output"
```

- Endpoint: `http://<cad-host-ip>:8000/mcp` (FastMCP default path).
- Host defaults to `127.0.0.1`, port to `8000`. LAN access requires explicit `0.0.0.0` and an appropriate firewall rule.
- `SW_MCP_HOST` / `SW_MCP_PORT` provide defaults; CLI arguments take precedence.
- `uvicorn` is optional and required only for HTTP. The default remains `stdio`; existing configurations need no change.
- Non-loopback listening requires `SW_MCP_TOKEN` and explicit `--allow-host`. Supply the actual IP/domain clients use; repeat for multiple hosts.
- Clients send `Authorization: Bearer <shared-secret>`. Browser clients additionally require `--allow-origin "https://client-domain"`.
- Keep Host/Origin checks enabled. Upstream private-endpoint checks covered handshake, 401, and invalid Host/Origin rejection.
- Protect public or untrusted-network traffic with a TLS reverse proxy or controlled tunnel.

Example remote-client configuration:

```jsonc
{
  "mcp": {
    "servers": {
      "solidworks": {
        "type": "remote",
        "url": "http://192.168.1.10:8000/mcp",
        "headers": { "Authorization": "Bearer <shared-secret>" }
      }
    }
  }
}
```

Consult your client's documentation for its URL/header field names. This transport uses the existing MCP process and COM lock.

### Retrieve previews and deliverables

Outputs within `--output-root` or `SW_MCP_OUTPUT_ROOT` receive `artifact_refs` with opaque `artifact_id`, `uri`, size, and SHA-256. The default permits only `solidworks-automation-artifacts` under the system temporary directory; set an explicit delivery directory.

- Call `cadstudio_read_artifact` with `{"params":{"artifact_id":"<id-from-result>"}}`; small images return PNG content blocks.
- Use `resources/read` with the returned `cad-artifact://delivery/...` URI for original binary files up to 8 MiB.
- For larger files, set `as_preview:false`, `offset`, and `max_bytes` on `cadstudio_read_artifact`. Follow `next_offset`, concatenate decoded base64 chunks, and verify SHA-256.
- Reads reuse Artifact Ledger. Changed files, out-of-bounds paths, and arbitrary path arguments cannot be read as verified artifacts.

Place remote inputs on the CAD host first; artifact access serves existing deliverables only. The artifact feature added one read-only tool while preserving the original 60 tool names and schemas.

## Smithery publishing

Root `manifest.json` follows MCPB with `tools_generated: true`. Build a standard package, then generate a Smithery package containing actual FastMCP `inputSchema` values:

```powershell
mcpb pack . .\dist\solidworks-automation-skill-1.3.0.mcpb
python .\scripts\build_smithery_mcpb.py `
  .\dist\solidworks-automation-skill-1.3.0.mcpb `
  .\dist\solidworks-automation-skill-1.3.0-smithery.mcpb
smithery mcp publish .\dist\solidworks-automation-skill-1.3.0-smithery.mcpb `
  -n <your-smithery-namespace>/solidworks-automation-skill
```

The upstream publishing workflow requires `inputSchema` in Smithery tool cards while MCPB 0.4 static `tools` disallows it. The script generates from the server registry to avoid maintaining two schema sets. Use a namespace you control.

## Client registration

The registrar supports Codex, Claude Code, Claude Desktop, Cursor, and Windsurf. Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\mcp-server\register_all_ai_mcp.ps1 -InstallDependencies
```

Register selected clients:

```powershell
powershell -ExecutionPolicy Bypass -File .\mcp-server\register_all_ai_mcp.ps1 -InstallDependencies -Clients codex,claude-code,cursor
```

Direct Node.js registrar for installers or CI:

```powershell
node .\mcp-server\register_all_ai_mcp.js --install-dependencies
```

Verify registration:

```powershell
codex mcp list
claude mcp list
```

The repository installer invokes the registrar. A client importing only skill files may not run installation scripts; register locally in that case.

For Codex only:

```powershell
powershell -ExecutionPolicy Bypass -File .\mcp-server\register_codex_mcp.ps1 -InstallDependencies
```

### Manual configuration

Substitute your local checkout path:

```json
{
  "mcpServers": {
    "solidworks": {
      "command": "python",
      "args": [
        "C:\\path\\to\\solidworks-automation-skill\\mcp-server\\server.py"
      ]
    }
  }
}
```

Equivalent client CLI examples:

```powershell
codex mcp add solidworks -- python C:\path\to\solidworks-automation-skill\mcp-server\server.py
claude mcp add --scope user solidworks -- python C:\path\to\solidworks-automation-skill\mcp-server\server.py
```

## Tool reference

Availability and acceptance status come from the capability registry. An exposed tool is not proof that every operation has been validated on your machine.

| Tool | Purpose | CAD changes / output writes |
|---|---|---|
| `cadstudio_resolve_backend` | Select Python/C#/C++/SWBasic/OCCT by capability, interface semantics, runtime, revision, and add-in evidence | No CAD modification |
| `cadstudio_write_open_format` | Write allowlisted .cadstudio.json to STEP/IGES/BREP/STL/OBJ/GLB/DXF/SVG/PDF/PNG, preview manifests/scenes, and geometry/hash evidence | Output files |
| `cadstudio_build_dxf_preview_scene` | Read allowlisted DXF into a new .scene.json without overwriting earlier files | Output files |
| `cadstudio_read_artifact` | Return PNG previews or bounded binary chunks by delivery ID; verify Ledger SHA-256 | No CAD modification |
| `cadstudio_check_dfm` | Declarative machining, sheet-metal, laser-cutting, printing, or molding checks; missing critical input blocks, passing rules still need review | No CAD modification |
| `cadstudio_check_routing` | Validate neutral endpoints, segments, lengths, bend radii, collision/clearance, supports, and Routing BOM | No CAD modification |
| `cadstudio_routing_preflight` | Probe Routing type libraries, add-in registration, and license evidence; block if missing | No CAD modification |
| `solidworks_addin_host_status` | Inspect C# assembly, HKCU/HKLM registration, in-process UI/events, and blocking codes | No CAD modification |
| `cadstudio_fea_preflight` | Probe CalculiX/Elmer without arbitrary commands | No CAD modification |
| `cadstudio_prepare_fea` | Generate versioned CalculiX .inp from FEA 1.0/1.1 requests without arbitrary scripts | Output files |
| `cadstudio_run_fea` | Run allowlisted linear or restricted nonlinear CalculiX static analysis; parse displacement, stress, and convergence | Output files |
| `cadstudio_run_fea_convergence` | Run 3–8 allowlisted meshes; compare displacement/stress changes in the final two | Output files |
| `cadstudio_review_advanced_geometry` | Validate neutral surface/mold plans; return pilot/blocked evidence | No CAD modification |
| `cadstudio_create_ocp_loft` | Generate ruled Loft STEP/BREP/STL from closed sections; reopen and verify B-Rep | Output files |
| `cadstudio_create_ocp_surface` | Generate supported smooth Loft, line/arc Sweep, closed-shell Knit, or open-surface Thicken from strict JSON with continuity samples | Output files |
| `solidworks_health_check` | Check Python dependencies, installation, Motion type library, and optional live connection | No CAD modification |
| `solidworks_connect` | Attach/start SOLIDWORKS and summarize the active document | Session |
| `solidworks_new_document` | Create part/assembly/drawing | CAD |
| `solidworks_create_basic_part` | Create box/cylinder, optionally save and color | CAD |
| `solidworks_open_document` | Open an existing document | CAD |
| `solidworks_add_component` | Add part/subassembly, optionally fixed | CAD |
| `solidworks_set_component_fixed` | Fix/float components by name keyword | CAD |
| `solidworks_save_document` | Save/save-as the active document | CAD |
| `solidworks_close_documents` | Close active/all documents; may discard unsaved changes | Session; unsaved changes may be lost |
| `solidworks_add_coincident_mate` | Add a coincident Mate between specified component planes/features | CAD |
| `solidworks_add_distance_mate` | Add a distance Mate between specified component planes/features | CAD |
| `solidworks_add_concentric_mate` | Mate cylinders by radius range, optionally locking rotation | CAD |
| `solidworks_set_appearance` | Color the active document or component | CAD |
| `solidworks_export_active` | Export STEP/STL/IGES/Parasolid/PDF/DXF | Output/review files |
| `solidworks_inspect_configurations` | Read configurations and active selection | No CAD modification |
| `solidworks_create_configuration` | Create/reuse using AddConfiguration3; optionally activate, rebuild, save, and read back | CAD |
| `solidworks_activate_configuration` | Switch configuration; verify active name and rebuild result | CAD |
| `solidworks_update_dimension` | Update exact named dimension with before/after, rebuild, and save evidence | CAD |
| `solidworks_set_custom_properties` | Write/read back file-level or configuration properties | CAD |
| `solidworks_batch_export_files` | Export multiple files/formats; verify current-run artifacts | Output/review files |
| `solidworks_export_assembly_bom` | Export component/property BOM CSV with required manual review | Output/review files |
| `solidworks_pack_and_go` | Package document and dependencies using native Pack and Go or explicitly labeled fallback | Output/review files |
| `solidworks_review_active` | Export multiple BMP views and JSON review | Output/review files |
| `solidworks_generate_drawing` | Generate DrawingSpec v1 GB/T/ISO SLDDRW, PDF, previews, review; associate COM dimensions with final PDF text | Output/review files |
| `solidworks_review_drawing` | Review DrawingSpec structure, layout, dimension chains, holes/slots, and final PDF text bounds | Output/review files |
| `solidworks_inspect_drawing` | Read sheets, views, dimensions, notes, tables, and BMP evidence | Output/review files |
| `solidworks_create_hole_feature` | Create blind/through holes, counterbores, countersinks, or straight slots with parameter evidence | CAD |
| `solidworks_inspect_hole_features` | Read B-Rep hole segments, compound holes, slot-end arcs, and positions | No CAD modification |
| `solidworks_add_rotary_motor` | Create Motion Study and constant-speed rotary motor in the active assembly | CAD |
| `solidworks_inspect_motion_studies` | Read studies, motor/force counts, and result freshness | No CAD modification |
| `solidworks_validate_motion_study` | Gate duration, type, motor count, and current calculated results | No CAD modification |

## Assembly examples

Create a cylinder:

```json
{
  "shape": "cylinder",
  "radius_mm": 25,
  "depth_mm": 50,
  "output_path": "C:\\temp\\cylinder.SLDPRT",
  "color": "#BFC4C8"
}
```

Add and fix a component in the active assembly:

```json
{
  "path": "C:\\temp\\base.SLDPRT",
  "x_mm": 0,
  "y_mm": 0,
  "z_mm": 0,
  "fix_component": true
}
```

Create a concentric Mate retaining rotation:

```json
{
  "component_a_keyword": "stand",
  "component_b_keyword": "impeller",
  "radius_a_min_mm": 4.5,
  "radius_a_max_mm": 5.5,
  "radius_b_min_mm": 11,
  "radius_b_max_mm": 13,
  "lock_rotation": false
}
```

Add axial positioning:

```json
{
  "component_a_keyword": "stand",
  "component_b_keyword": "impeller",
  "feature_a_name": "Front Plane",
  "feature_b_name": "Front Plane",
  "distance_mm": 42
}
```

## Motion and compound-hole examples

The active assembly must contain a stationary shaft/post and an unfixed impeller whose concentric Mate does not lock rotation:

```json
{
  "shaft_component_keyword": "stand",
  "rotor_component_keyword": "impeller",
  "shaft_radius_min_mm": 4.5,
  "shaft_radius_max_mm": 5.5,
  "rotor_radius_min_mm": 10.5,
  "rotor_radius_max_mm": 11.5,
  "rpm": 60,
  "study_name": "Impeller_60RPM_ContinuousRotation",
  "motor_name": "ImpellerRotaryMotor_60RPM",
  "duration_seconds": 4,
  "calculate": true,
  "play": false
}
```

Create a counterbore:

```json
{
  "feature_kind": "counterbore",
  "center_x_mm": 20,
  "center_y_mm": 15,
  "diameter_mm": 6,
  "secondary_diameter_mm": 12,
  "secondary_depth_mm": 4,
  "plane_name": "Front Plane",
  "feature_name": "H1_Counterbore"
}
```

Validate the Motion Study:

```json
{
  "study_name": "Impeller_60RPM_ContinuousRotation",
  "expected_study_type": 1,
  "minimum_duration_seconds": 4,
  "minimum_motor_count": 1,
  "require_results": true
}
```

## Boundaries and design principles

- No arbitrary Python/VBA execution tool is exposed.
- `cadstudio_` identifies headless/gate tools; `solidworks_` identifies native tools.
- COM operations are serialized and errors include suggested actions.
- Basic parts, complex holes/slots, components, common Mates, fix/float, appearance, exports, reviews, rotary motors, and Motion result gates have wrappers. DFM/Routing/FEA/advanced geometry use controlled entry points.
- Only documented restricted geometry routes are executable. General freeform surfaces, unrestricted G1/G2 guarantees, and mold automation cannot be inferred from plan validation or sampled evidence.
- The simplified headless PDF fallback embeds a bundled font through PyMuPDF to preserve Turkish title characters. Without PyMuPDF, it transliterates Turkish letters to ASCII and reports that limitation; other non-ASCII characters are shown as escapes. This fallback still does not include the full dimension text of the normal drawing renderer.
- Motion/Simulation licensing affects calculation. Missing legitimate add-ins/licenses return `blocked`; licensing is never bypassed.

Five protected experimental tools cover native circular-profile sweeps, STEP import, body inspection/exclusion, and position-preserving component replacement. See [native wire tool specifications and review requirements](../docs/native-wire-tools.md).
