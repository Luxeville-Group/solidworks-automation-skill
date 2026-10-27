# V2 Execution Core — Internal Reliable Execution Layer

> Positioning: Execution Core is an **internal implementation**, not a user entry point, daemon, or independent Runtime service.
> It is not a fourth entry point and does not replace higher-level Planning by Codex / Claude.

## 1. Motivation

Before V2, reliability concepts were distributed across Skill, MCP, Worker, Reviewer, Artifact Ledger, and other modules
(capability gates, backend routing, policy approval, leases, heartbeats, stale recovery, file-fact review, geometry evidence, and JSONL events),
but **had not been consolidated into a unified, reusable, testable execution reliability layer**.

V2 turns these existing capabilities into a lightweight execution layer with this principle:

> AI may reason freely, but execution must be controlled, verifiable, recoverable, and traceable.

## 2. Architecture

```
LLM Agent (Codex / Claude / Cursor / OpenClaw)
  ↓
Skill / MCP / CAD Studio (three unchanged user entry points)
  ↓
Execution Core (scripts/core/)
  ├─ State (state.py)
  ├─ Capability Facade (capability.py)
  ├─ Trace (trace.py)
  ├─ Verification Adapter (verification.py)
  ├─ Recovery Decision (recovery.py)
  └─ Execution Orchestration (execution.py)
  ↓
Backend Router (scripts/capabilities.py + capabilities.yaml)
  ↓
Tools / MCP / Scripts (Python COM / C# PIA / OCCT / ...)
  ↓
External CAD Software
  ↓
Verification → Recovery Decision → Artifacts / Evidence / Trace
```

**Consistent terminology** (do not interchange Runtime Manager / Agent Engine / Workflow Engine / Orchestrator Core):

- **Skill** = Domain knowledge, capability descriptions, SOPs, and open-capability rules
- **MCP** = Standardized Tool Protocol
- **Capability Registry** = `capabilities.yaml` + adapter
- **Backend Router** = Selects execution backends by capability / environment / version
- **Execution Core** = Execution Reliability Layer (essentially a lightweight Agent Runtime)
- **Worker** = Job Processor
- **Reviewer** = Result Verification
- **Artifact Ledger** = Delivery Facts (final delivery facts)
- **Trace** = Execution History (history of the execution process)
- **Golden Workflow Eval** = Reliability Benchmark

## 3. State (`state.py`)

A lightweight execution state model, **not tightly coupled to the CAD Studio Queue Schema**, reusable by Worker / MCP / CLI.
It does not implement a complex FSM; a minimal transition allowlist blocks transitions such as `FAILED → COMPLETED` and `BLOCKED → COMPLETED`.

- `RunStatus`: created / running / verifying / retrying / blocked / failed / completed
- `StepStatus`: pending / running / success / failed / verifying / retrying / blocked
- `VerificationStatus`: PASS / WARN / FAIL / BLOCKED
- `RunContext` / `StepRecord` / `ExecutionResult` / `VerificationResult` / `RecoveryDecision`

Everything is JSON-serializable and carries `schema_version`; only `arguments_summary` / `result_summary` summaries are stored,
not complete prompts, API keys, secrets, or unnecessary absolute paths.

## 4. Capability Facade (`capability.py`)

**Not a new Registry**: a thin Adapter over `scripts/capabilities.py` + `capabilities.yaml`:

- `get_capability` / `get_capability_status` / `get_operation_route`
- `resolve_backend` (delegates directly to `resolve_operation_backend`)
- `get_backend_candidates` / `requires_review` / `capability_gap`

`capabilities.yaml` remains the sole capability source of truth; no second configuration such as `tool_registry.yaml` is introduced.

## 5. Execution (`execution.py`)

`execute_with_core(...)` connects the orchestration steps:

```
RunContext + StepRecord
  → Existing Handler (called unchanged, with raw_result retained)
  → ExecutionResult (minimal normalization; original exceptions returned)
  → Verification Adapter (when requires_review)
  → Recovery Decision (on failure/blocked)
  → Trace
  → ExecutionAssessment (sidecar)
```

**Outside its responsibility**: Queue claim / lease / heartbeat / approval / policy / stale recovery / Ledger implementation /
Reviewer implementation / Backend Router implementation / actual retry / actual backend switching / replanning / networking.

## 6. Verification (`verification.py`)

Verification Adapter only translates check results into a consistent representation:

- `verify(...)` invokes the existing Reviewer (injected callable or existing result) and returns a unified `VerificationResult`;
- Normalizes historical states: `pass/warn/warning/review_required → PASS/WARN`, `fail/failed → FAIL`,
  `blocked → BLOCKED`; unknown states safely degrade to `BLOCKED`;
- Aggregation: `BLOCKED > FAIL > WARN > PASS`, respecting `severity` / `required` / `optional`;
- **`reviewer_result` takes precedence over `reviewer`** to avoid repeating the same review.

Core rule: **Tool / Handler success ≠ task success**. Capabilities requiring review may complete only after Verification
PASS with `manual_review_required=false`. WARN / FAIL / BLOCKED and pending human review cannot become completed. Required boolean flags that are false in structured execution results cause failure; ambiguous types or null critical evidence cause blocked. A top-level PASS cannot override a required check's FAIL.

## 7. Recovery Decision (`recovery.py`)

Answers only "What action should follow this failure?"; it **does not execute that action**.

- `ErrorKind` (10 categories): transient / invalid_argument / environment_missing / tool_unavailable /
  backend_unavailable / verification_failed / user_action_required / policy_blocked / capability_gap / fatal
- Deterministic `classify_error(...)` priority: explicit error_kind → structured error_code → existing Result state
  (policy > capability > verification > execution) → exception type → message keywords → unknown becomes FATAL
- `decide(...)` → `RecoveryDecision` (retry / fallback_backend / replan_required /
  user_action_required / block / fail), with bounded retries (`DEFAULT_MAX_RETRIES = 2`)

**Important: Recovery Decision ≠ Recovery Execution.** This version only produces and records decisions;
**automatic retry / fallback / replan is not enabled by default**. The Worker / higher-level Agent decides whether to execute an action.

Safe default: uncertainty → BLOCK / FAIL / REPLAN, never retry by default. `POLICY_BLOCKED → block`;
Recovery cannot bypass Policy Gate.

## 8. Trace (`trace.py`)

Reuse append-only JSONL under the existing `queue/events/`; **do not create independent Trace storage**:

- Events: `run.started / step.started / tool.called / tool.succeeded / tool.failed /
  verification.* / recovery.* / run.completed / run.failed / run.blocked`;
- Additive schema: `run_id / trace_id / step_id / parent_step_id / ...` are all optional; older events remain readable;
- `redact` provides fallback sanitization (prompt / api_key / token / secret / ...);
- Trace write failures do not alter execution results; observability is a side-channel capability.

Separate responsibilities: **Artifact Ledger = final delivery facts; Trace = execution history**. Do not overlap them.

## 9. Worker Integration (minimal intrusion)

`queue_worker.process_job` continues reusing the existing Handler and Review Gate:

```
Job → Policy / Approval (still before Execution Core)
    → Execution Core wraps Existing Handler
    → Existing Reviewer Gate (still runs only once)
    → Verification Adapter + Recovery Decision (review results feed the existing Gate)
    → Existing terminal-state mapping (passed / review_required / failed / blocked / cancelled)
```

- Policy / Approval / Cancellation / claim lock / lease / heartbeat / stale recovery / quarantine
  **all unchanged**;
- Existing Handler remains the sole actual execution implementation;
- Queue / Worker / Reviewer / Artifact Ledger are not rewritten;
- New `executionAssessment` / `verificationAssessment` / `recoveryDecision` fields are optional sidecars.
- Worker delays Core completion until the existing Review Gate finishes, then aligns Queue and Core terminal states, avoiding Core completed followed by Queue failed.

## 10. Capability Gap

Missing capabilities/backends return structured `CAPABILITY_GAP` (`agent_resolution_required`) and return control
to the higher-level Agent. **Execution Core does not access the network or generate tools automatically**; the Agent continues under SKILL.md:

```
references → official API / SDK → alternate backend → minimal implementation → verification
```

`Tool Missing != Capability Missing`: an existing capability with an unavailable tool → `replan_required`
(the higher-level Agent attempts Tool Composition); a missing capability itself → `CAPABILITY_GAP`.

## 11. Reliability Eval (`tests/evals/`)

`golden-workflows.yaml` is the sole Golden Workflow source of truth. Eval derives 37 deterministic scenarios,
grouped by nominal / recovery / fault_injection / guardrail, using Fake Handlers/Reviewers to verify
execution control logic. Metrics have four groups: Nominal / Robustness / Safety / Overall Diagnostic.
See [`v2-evaluation.md`](v2-evaluation.md) and [`v2-regression-report.md`](v2-regression-report.md).

## 12. Compatibility

- Skill usage, the original 60 MCP Tool Names / Input Schemas, CLI commands, and Queue Schema remain compatible; read-only artifact tools and optional HTTP transport are added;
- `capabilities.yaml` remains the sole source of truth, and `golden-workflows.yaml` remains backward-compatible;
- All new fields are additive / optional;
- The 2026-10-08 Scheme B fixes address execution facts, sketches/patterns, and resource lifecycles, with acceptance scoped to SolidWorks 2026. See [`scheme-b-reliability.md`](scheme-b-reliability.md).
