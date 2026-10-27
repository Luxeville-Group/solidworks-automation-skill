# SolidWorks Automation Skill — Türkçe / English

[**Türkçe başlangıç kılavuzu**](README.tr.md) · **English documentation** · [Terminology / Terimler](localization/TERMS.tr-en.md)

AI skill and MCP toolkit for supervised desktop CAD automation. Codex, Claude, Cursor and other agents use scripts and native CAD APIs to create artifacts and check the results.

This is the **Luxeville-Group Turkish/English fork** of [wzyn20051216/solidworks-automation-skill](https://github.com/wzyn20051216/solidworks-automation-skill). Desktop UI and guided interactions use Turkish with English CAD terminology; technical documentation and code comments are English. CLI/API diagnostics may be Turkish, English or bilingual. See the [language policy](localization/README.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-stdio--server-blue)](mcp-server/README.md)

```text
User → Agent (Codex / Claude / Cursor) → Skill / MCP → CAD APIs → Artifacts + Evidence
```

The agent interprets intent, checks APIs and plans operations. CAD Studio's Worker uses the execution core to record execution, check evidence and select bounded recovery actions. Direct Skill and MCP workflows use their documented scripts, tool checks and review steps; they do not all pass through the complete Worker execution chain. **A successful tool call does not establish a completed engineering task.**

## What it does

The normal SolidWorks path uses Python COM automation, with C# or native bridges for specific interfaces. It calls CAD APIs rather than clicking screen coordinates. SolidWorks may still open a visible window; some workflows capture previews or require manual review. The desktop workbench is an optional interface to the same capabilities.

A typical workflow is: requirements → structured plan → native `SLDPRT + SLDDRW` → PDF/export → geometry and evidence review.

| Example | Capability | Upstream status |
|---|---|---|
| [M6×1 threaded hole](subskills/solidworks-threaded-holes/README.md) | Metric Tap Thread with post-rebuild readback | `verified` |
| [CNC mounting base](subskills/solidworks-fillet-chamfer-cnc/README.md) | Semantic edge selection, variable-radius, face/full-round/setback fillets | `stable`, within documented limits |
| [Involute spur gear](references/gears.md) | Solid driven by module, tooth count and pressure angle | `pilot` |

Upstream verification records apply to their stated versions and samples. Translating this fork does not independently repeat native CAD acceptance or certify a design for manufacture.

## Installation and entry points

Choose one entry point; Skill, MCP and CAD Studio share the same scripts, capability registry and evidence system.

| Entry point | Suitable for | Optional workbench GUI |
|---|---|---|
| Skill | An agent client that reads `SKILL.md` and runs local scripts | Not required |
| MCP | Codex / Claude / Cursor / Windsurf tool calls | Not required |
| CAD Studio | Managing projects, tasks, previews and deliveries in a desktop app | Required |

For native SolidWorks work, use Windows, an installed/licensed SolidWorks environment and Python 3.10+ with the relevant dependencies. Native operations currently target SolidWorks 2026 acceptance. Other versions require capability checks.

### Skill from this fork

With Node.js/npm and Git installed, the existing installer is:

```powershell
npx github:Luxeville-Group/solidworks-automation-skill
```

This installer detects common agent skill directories, copies the repository, installs base Python dependencies and attempts MCP registration. Review [install.js](install.js) before use.

**Node.js is not required by the Python CAD execution layer.** Without Node/npm, clone this fork into a skill directory recognized by your agent, install the Python dependencies, and use the skill or Python MCP server directly. Do not run the npm installer merely to use the Python API. A dedicated no-Node PowerShell installer is not included in this localization change.

### MCP

Use the local server from this checkout; see [MCP setup](mcp-server/README.md). The all-client JavaScript registrar requires Node, while the Python server itself does not. An upstream registry package is not a release of this localized fork.

### CAD Studio

Use the source startup/build instructions in [the desktop guide](apps/desktop/README.md) and [user manual](docs/CAD_STUDIO_USER_MANUAL.md). Do not assume upstream Windows installers contain these translations. Fork releases must be built and published separately.

Run environment diagnostics from the repository root:

```powershell
python scripts/cad_doctor.py
```

## Architecture

```text
User / Agent
  ├─ Skill / MCP → Scripts / Tools → Backend APIs
  └─ CAD Studio → Worker → Execution Core → Existing Handlers → Backend APIs

Shared capability registry and backend routing
  → Python COM / C# / OCCT
  → CAD Software / Geometry Kernel
  → Artifacts + Evidence
```

- **Root skill:** connection, document management, modeling wrappers, review and MCP.
- **Subskills:** specialist workflows for drawings, threaded holes, CNC fillets, VibeCAD and AutoCAD; loaded when relevant.
- **Execution core:** reusable state, verification, recovery decisions and traces, integrated around Worker handlers. MCP reuses result normalization; direct script execution still follows the Skill's review instructions. It is an internal layer, not another service to start.
- **Capability gap:** returns structured `CAPABILITY_GAP` so the agent can consult references or official API/SDK documentation, implement a minimal extension and verify it.

```text
Existing Tools → Tool Composition → Backend Fallback → Capability Gap
  → Agent research → Minimal implementation → Verification
```

The execution core does not automatically download and execute unknown code. See [execution-core architecture](docs/architecture/execution-core.md).

## Reliability and limits

The upstream V2 benchmark contains 37 deterministic scenarios covering normal execution, injected failures, backend fallback, capability gaps and policy gates.

| Upstream benchmark metric | Recorded baseline |
|---|---|
| Nominal workflows | 10/10 first pass in baseline v3; warnings await manual review |
| Injected false-completion cases | All detected |
| Escaped false completion | 0 in that deterministic benchmark |
| Scheme B regression record | [Reliability repairs and acceptance](docs/architecture/scheme-b-reliability.md) |

These are fake-handler/reviewer and fault-injection results, **not production success rates or a service-level guarantee**. See [evaluation details](docs/architecture/v2-evaluation.md).

Scheme B retains the execution architecture while addressing failure states, native patterns, sketch editability and document ownership, with optional HTTP and verifiable artifact retrieval. Existing MCP tool names and input schemas remain compatible.

| Category | Scope | Status varies by operation |
|---|---|---|
| Modeling | Parts, sketches, extrusions, revolutions, gears, sheet metal, weldments | `verified` / `pilot` |
| Assembly | Components, mates, interference checks and exploded views | See operation evidence |
| Drawing | GB/T drawings, dimension chains, hole tables and BOM | `verified` / `pilot` |
| Export | STEP / STL / IGES / PDF / DXF / DWG | Depends on backend and format |
| Motion | Rotary motors and result gates | `pilot` |
| FEA | CalculiX linear/nonlinear orchestration and audits | `pilot` |
| DFM / Routing | Manufacturing and routing review | `pilot` |
| Surface / Mold | Restricted Loft/Sweep/Thicken and mold planning | `pilot` |
| AutoCAD | DWG/DXF, layers, annotations and previews | `verified` / `pilot` / `blocked` |
| Open formats | OCCT STEP/BREP/STL/OBJ/GLB and other outputs | Within recorded limits |

`verified` means evidence exists for the stated native environment and scope; `stable` denotes established regression coverage; `pilot` requires further validation/manual review; `blocked` prohibits automatic delivery in the current environment.

The authoritative per-operation versions, dependencies and limits are in [capabilities.yaml](capabilities.yaml). Historic evidence includes SolidWorks 2024/2026 and AutoCAD 2024; this is not a blanket compatibility guarantee. Engineering drawings retain their declared GB/T/ISO rules; translating the interface does not select Turkish standards automatically.

## Without SolidWorks

Some open-format operations can run through isolated OCCT/OCP processes:

`STEP · IGES · BREP · STL · OBJ · GLB · DXF · SVG · PDF · PNG`

Native `SLDPRT / SLDASM / SLDDRW` production and acceptance still require SolidWorks.

## Assembly interference check

`solidworks_interference_check` uses `IAssemblyDoc.InterferenceDetectionManager`, calls `GetInterferences()`, reads `IInterference.Components` and volumes, and finishes with `Done()`. Hidden bodies and ignored results are included; intersections within a single multibody part are excluded.

Calculation, count-read, array-count or cleanup failures return `blocked`, never a false zero-interference result. Suppressed components are excluded; zero results still require checking resolved components and design intent.

Upstream recorded 26 offline regressions for call order, failure handling and SI volume conversion, and a successful zero-interference MCP case on SOLIDWORKS 2026 SP4.1 (34.4.1) / Python 3.10. Nonzero readback has offline evidence only.

## Documentation

| Topic | Link |
|---|---|
| Turkish onboarding | [README.tr.md](README.tr.md) |
| Turkish/English terminology | [Terminology](localization/TERMS.tr-en.md) |
| MCP setup | [MCP README](mcp-server/README.md) |
| CAD Studio | [User manual](docs/CAD_STUDIO_USER_MANUAL.md) |
| Architecture / evaluation | [Execution core](docs/architecture/execution-core.md) · [Evaluation](docs/architecture/v2-evaluation.md) |
| Capability matrix | [capabilities.yaml](capabilities.yaml) |
| Specialist workflows | [SUBSKILLS.md](SUBSKILLS.md) |
| API / backend reference | [references/](references/) |
| Troubleshooting | [Troubleshooting](references/troubleshooting.md) |
| Runnable examples | [examples/](examples/) |

## Contributing and attribution

Priorities include broader native validation, reliable capability routing, workbench observability and verified specialist workflows. Reuse existing backends, add meaningful tests and evidence, and never label an unverified capability `verified`. See [CONTRIBUTING.md](CONTRIBUTING.md).

[MIT license](LICENSE) · [Fork issues](https://github.com/Luxeville-Group/solidworks-automation-skill/issues) · [Original project](https://github.com/wzyn20051216/solidworks-automation-skill)

Original authors and third-party case attribution are preserved. Historical upstream media may retain its original UI language and is not presented as a localized demonstration.
