# V2 Release Notes (Draft)

> SolidWorks Automation Skill V2 — internal reliability architecture upgrade.

## Added

- **Execution Core** (`scripts/core/`): connects State / Capability / Trace / Verification / Recovery
  into an internal execution chain wrapping existing Handlers.
- **State model** (`state.py`): lightweight Run/Step/Execution/Verification/Recovery states.
- **Capability Facade** (`capability.py`): thin adapter reusing `capabilities.yaml` as the sole source of truth.
- **Verification Adapter** (`verification.py`): normalizes existing Reviewer results to PASS/WARN/FAIL/BLOCKED.
- **Recovery Decision Layer** (`recovery.py`): 10 error categories + six recovery decision types; decisions only, with no execution by default.
- **Trace integration** (`trace.py`): reuses append-only execution history in `queue/events/`.
- **Golden Workflow Reliability Eval** (`tests/evals/`): deterministic reliability benchmark.

## Preserved

- Existing Skill usage, MCP Tool Names / Input Schemas, CLI commands, and CAD Studio Queue state semantics remain unchanged.
- Worker / Reviewer / Artifact Ledger / Policy Gate are not rewritten.
- `capabilities.yaml` remains the sole capability source of truth; `golden-workflows.yaml` is backward-compatible.
- All new fields are additive / optional.

## Metrics (Deterministic Execution Reliability Benchmark, 37 scenarios)

| Metric | Value |
|---|---|
| Nominal First-Pass Success | 100% (10/10, baseline v3) |
| Nominal Task Success | 100% |
| Failure Detection | 100% |
| Policy Block Accuracy | 100% |
| Capability Gap Accuracy | 100% |
| Backend Fallback Decision Accuracy | 100% |
| False-Completion Detection | 100% |
| Escaped False-Completion | 0% |

## Limitations

- Scheme B on 2026-10-08 changed warning/manual review to blocked and added real SolidWorks 2026 sketch, pattern, document-ownership, and remote-artifact acceptance. See [`scheme-b-reliability.md`](scheme-b-reliability.md). Older versions are outside current support and acceptance scope.

- This benchmark is **synthetic / deterministic** (Fake Handler/Reviewer + fault injection),
  **not** a real-user success rate, all-scenario SolidWorks success rate, measure of LLM intelligence, or production SLA.
- Execution Core does not perform automatic LLM Planning; higher-level Agents retain that responsibility.
- It does not discover Web / API capabilities automatically; Capability Gaps return to the higher-level Agent.
- Recovery makes **decisions** only. Automatic retry / fallback / replan actions remain controlled by Worker / higher-level Agents and are not enabled by default.

## Docs

- [`docs/architecture/execution-core.md`](execution-core.md)
- [`docs/architecture/v2-evaluation.md`](v2-evaluation.md)
- [`docs/architecture/v2-regression-report.md`](v2-regression-report.md)
- [`docs/architecture/v2-audit.md`](v2-audit.md)
