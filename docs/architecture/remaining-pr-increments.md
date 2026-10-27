# Incremental Fixes from Remaining PRs (2026)

Baseline main: `f7de34f`. This work applies Scheme B to #8/#11/#23/#24/#25, retaining verified interference handling, Queue, Reviewer, Artifact Ledger, MCP names, and input contracts. Native acceptance is scoped to SolidWorks 2026.

| Source | Current implementation |
|---|---|
| #8 | Path import is already covered by `9d19194`; this run enumerates the real 2026 Motion type library and treats the original PR as superseded where covered |
| #11 | Reuse existing light/dark SVGs and the update workflow; restore README embedding without restoring an external dynamic-image service dependency |
| #23 | Port the original author's short-lived fallback-process approach; verify PID/2026 version, bind to the parent instance, and explicitly block unknown ownership/timeouts; retain main's correct per-item interference volume; improve feature error/warning, empty-view, degenerate-envelope, and file-load diagnostics |
| #24 | Retain the original author's host-protection commit; strictly validate HTTPS, host, port, URL credentials, and commit path at request time; reject redirects, bound reads, and verify SHA-256 before caching |
| #25 | Retain the original author's host-protection commit; complete PATH fallback for four Agents while preserving explicit user configuration; consistently check canonical paths for JSON/SQLite, bound JSON reads, and retain clearly fake credential fixtures |

The Pack and Go subprocess is a one-shot COM marshaling backend, not a new persistent service. Ownership depends on the actual PID, not whether CreateObject/Dispatch returns an object. Unknown snapshots, missing target documents, PID mismatches, and timeouts all block execution, preventing another staging/retry pass from overwriting unconfirmed output. The 2026 manifest depends on the active document; fallback explicitly activates the specified source and verifies the returned document path.

Local comtypes document-array marshaling raises KeyError(9). Fallback reads the manifest through a same-PID pywin32 observer, while actual writing remains isolated in the subprocess. It closes only documents explicitly opened by this run; preexisting source files and users' unsaved documents do not belong to the subprocess.

Errors and warnings use separate enumerations from the local official SDK. Original values are retained, and stable machine error codes enter Core/MCP. GetErrorCode2 distinguishes warnings from errors; incomplete evidence still requires human review.

Verification and boundaries:

- Forced comtypes fallback on 2026 SP1.1 genuinely packaged an assembly and two parts. After save-and-reopen, both references pointed into the delivery directory. The parent proxy, unsaved documents, and open-document list were preserved; the test instance was cleaned up afterward.
- Independent fault cases cover ownership, timeouts, JSON/UTF-8, error/warning bitmasks, download redirects and pinned commits, Agent name compatibility, and configuration paths.
- A real healthy part on 2026 SP1.1 returned healthy status for 23 top-level features, passed review, and produced four real BMPs. An empty drawing failed; a damaged SLDPRT returned original error bitmask `2097152`, classified as `SW_FILE_REQUIRES_REPAIR`. The document list was empty after testing.
- Full local Python suite: 854 passed; Core/Eval with COM imports disabled: 125 passed; all 61 tool names and input Schemas exactly matched the baseline. Skill/MCP/release consistency checks passed, with 220 embedded runtime files.
- Nine frontend tests and the production build passed. Toolchain security advisories discovered during acceptance led to Vitest 4.1.11 and source-map-js 1.2.2 upgrades; a repeat audit reported zero advisories. Only the relevant versions and lockfile changed, not application interactions.
- A real STEP download from a pinned FreeCAD GitHub commit contained 132515 bytes, with SHA-256 matching the manifest. Separate offline failure cases cover caching, invalid sources, and tampered content.
- The local machine lacks file-symlink creation permission, so that Rust branch is not claimed as locally verified. GitHub CI forbids silent skipping of the branch and actually passed the out-of-bounds symlink rejection case. Canonical-path checks are not claimed as a complete filesystem sandbox against an attacker with equal privileges.
- A security-scan advisory does not automatically establish an exploitable vulnerability. XML rejection belongs to the test parser for generated SVG; no new production XML parsing capability is claimed.
- No duplicate interference tool was added; the existing `solidworks_interference_check` is reused, leaving MCP at 61 tools.

These features do not establish complete mold design, mold-flow analysis, design-check certification, or older-version compatibility. Final test/CI results accompany the integration PR's acceptance record.

Toolchain fix sources: [official Vitest security advisory](https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9), [source-map-js security advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q). These concern development/test/build dependencies and do not justify claiming that the released CAD application has been attacked.
