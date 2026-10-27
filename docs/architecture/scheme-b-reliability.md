# Scheme B: Reliability Fixes and Acceptance for the Existing Architecture

2026-10-08; support and native acceptance target SolidWorks 2026. The implementation baseline is `592e655`; community PR #21's commit history is preserved while execution and delivery contracts for related issues are repaired.

## Changes and actual causes

| Problem | Cause | Fix and acceptance boundary |
|---|---|---|
| Failed execution still shows success | Non-exception returns treated as success; Core completes before final Review | Required false flags fail; unknown evidence blocks; a required Review FAIL cannot be overridden by top-level PASS; completed requires PASS and no human review; align Queue/Core terminal states |
| #7 sketches lack design parameters | Geometric coordinates mistaken for constraints/dimensions; no save-and-reopen verification | Add dimensions/relations to basic circles/rectangles; read back fully-defined state, dimensions, and Fix; check that a feature consumes the sketch; complex sketches still need design parameters and human review |
| #14 unstable patterns | Incorrect native members/signatures; unreliable seed-feature and direction-entity selection | Exact seed feature, real parallel straight edges, 20-argument linear pattern; explicit axis for circular patterns; stop immediately on selection failure |
| #5/#15 process/document lifecycle | Dispatch does not establish a new process; starting again before ROT readiness can duplicate instances; documents accumulate | Read PID/actual Revision and wait for existing instances; clean up only current-run registered documents and confirmed owned empty instances; default eight-document budget; block creation when inventory is unreadable |
| #20/#22 remote clients receive only local paths | Only stdio available; default HTTP Host validation mismatches remote addresses; paths are not remote file contents | Add optional HTTP to the same MCP with explicit Host/Origin and Bearer; reuse Ledger to register opaque artifact IDs; return PNG content blocks/raw resources/bounded chunks and verify SHA-256 |
| #12 missing injection-molding DFM entry | Existing process allowlist/rule dispatch lacks injection molding | Add `injection_molding`, reusing NeutralCadDocument, Profile, and reports; screen declared draft, rib thickness, wall-thickness variation, undercut strategy, and gate/ejector/cooling-channel spacing |

Retain Worker, Queue, Reviewer, Artifact Ledger, Policy Gate, and the startup mutex. Recovery still generates decisions only. Every original MCP tool's name and full Input Schema matches the 60-tool baseline; adding `cadstudio_read_artifact` brings the total to 61. Default transport remains stdio; HTTP is an optional transport in the same process.

## Verification results

- Windows/Python 3.12 full pytest: 810 passed, with no skips, failures, or warnings. Skill self-check passed; MCP verified 61 tools; release consistency passed, with 217 embedded runtime files.
- Core/Eval with `pythoncom`, `win32com`, and `comtypes` imports disabled: 125 passed.
- The 37 deterministic scenarios continue using `golden-workflows.yaml`. Baseline v3 nominal is 10/10; warning is a guardrail and blocked; raw completion is 21/37 (diagnostic only), with zero false-success leakage.
- SolidWorks 2026 SP1.1 / Revision 34.1.1: real B-Rep and analytical volumes matched for three-hole linear and four-hole circular patterns. Saved/reopened sketches have dimensions, no Fix, and are consumed by features. Changing thickness from 8→10 mm preserves hole diameters and centers.
- In the same real CAD test instance, document budgeting prevented extra creation. Session cleanup closed only its own documents, preserving a simulated user's unsaved document and process; the test instance cleaned itself up at the end.
- A real native model was exported to STEP over HTTP and retrieved through an MCP resource: 31,651 bytes, matching SHA-256 `87388f90be31e299eb4d4e3c6dd12e4310d690ab08c16fe1be40552b10eb9ae2`. The read-only tool converted BMP to a PNG content block; visual review confirmed the three-hole model. Review remains `review_required`.
- Independent HTTP protocol tests verify handshake, tool discovery, 401, invalid Host/Origin rejection, PNG, and binary resources; injection-molding rules have separate real CLI file-output tests.

## Running and reviewing

From the repository root, with dependencies installed in Python 3.12:

```powershell
python scripts/sync_bundled_skill.py
python -m pytest -q
python scripts/validate_skill.py
python scripts/validate_mcp.py
python scripts/release_check.py
python tests/evals/runner.py
```

Real-machine tests require no SolidWorks instance currently in use and a new output directory:

```powershell
python tests/solidworks_reliability_b_regression.py --output C:\cad-test\reliability-b-2026
```

`report.json` records volume, hole locations, sketch evidence, and document cleanup results. The script is excluded from default pytest; CI without SolidWorks does not pretend to complete native acceptance. For HTTP deployment and artifact reads, see [`../../mcp-server/README.md`](../../mcp-server/README.md).

## Known limitations

- Current scope schedules no compatibility implementation or real-machine verification for older SolidWorks versions; retained general COM defenses do not constitute an older-version support commitment.
- Real-machine evidence covers only the explicit scenarios above; it does not guarantee that every complex part, third-party add-in, or heavy workload will avoid crashes.
- Injection molding remains `pilot` declarative rule screening. It does not automatically recognize complete B-Rep draft/undercuts or integrate mold flow; passing rules still requires engineering review. Users/processes/suppliers must explicitly declare thresholds; these are not universal certified material values.
- HTTP acceptance used a local service, remote Host headers, and a real MCP client; cross-machine networking, firewalls, and TLS proxies were not verified. Input uploads and concurrent CAD writes are outside this scope.
- Large-file chunks are content-verified on each read and suitable for delivery retrieval; large-file upload and resumable upload are not implemented.
- Follow-up after 2026-10-08 adapts useful increments from #23/#24/#25: fallback-process ownership, isolated Pack and Go, health, load diagnostics, downloads, and desktop boundaries. See [`remaining-pr-increments.md`](remaining-pr-increments.md) for that acceptance.
