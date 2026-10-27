# SolidWorks Automation Skill V2 Architecture Audit

> Version: Phase 1 (architecture audit)
> Status: awaiting confirmation before Phase 2
> Scope: complete review of the upstream `wzyn20051216/solidworks-automation-skill` main branch
> Principle: audit before code changes; this document records facts and a minimal change proposal, not implemented code.

---

## 0. Audit scope and method

Read in full:

- Top-level documents: `README.md`, `SKILL.md`, `SUBSKILLS.md`, `capabilities.yaml`, `golden-workflows.yaml`
- Routing/capabilities: `scripts/capabilities.py`, `scripts/backend_router.py`, `references/language-backend-routing.md`
- Review/preflight: `scripts/sw_review.py`, `scripts/sw_preflight.py`
- Desktop runtime under `apps/desktop/cad_workbench/`: `queue_worker.py`, `reviewer_gate.py`, `artifact_ledger.py`, `worker_health.py`, `agent_contracts.py`, `agent_providers.py`, `knowledge_retrieval.py`, `engineering_orchestrator.py`, `core.py`
- MCP: `mcp-server/server.py` (approximately 3500 lines), `mcp-server/README.md`
- CLI: `scripts/cad_studio.py`
- Documentation: `docs/agent-framework/enterprise-agent-control-plane.md`, `docs/product-mvp-spec.md`, `docs/skill-map.md`
- Tests: `tests/fakes.py`, `tests/test_cad_reliability.py`, `tests/test_workbench_queue_worker.py`, and the broader test directory
- Packaging/CI: `pyproject.toml`, `scripts/sync_bundled_skill.py`, `.github/workflows/windows-cad-regression.yml`

Audit conclusion: **This project already contains reliability concepts far beyond a typical Skill**: a capability source of truth, backend routing, policy gates, queue leases, heartbeats, stale recovery, Artifact Ledger, Reviewer Gate, JSONL events, and geometry evidence. They are **distributed across modules rather than consolidated into a unified, reusable, testable Execution Core**. V2 should **engineer these existing capabilities into a lightweight execution reliability layer**, without rewriting them, adding user entry points, or building a general-purpose Agent Framework.

---

## 1. Actual current architecture

### 1.1 Three user entry points (confirmed; unchanged)

| Entry point | Implementation | User interaction |
|---|---|---|
| **Skill** | `SKILL.md` + `scripts/` + `references/` + `subskills/` | After installation, talk to Codex / Claude / Cursor / OpenClaw; the Agent reads SOPs and calls scripts |
| **MCP** | `mcp-server/server.py` (FastMCP + Pydantic, stdio) | After installation, the Agent invokes tools automatically |
| **CAD Studio** | `apps/workbench-ui/` (React+Tauri frontend) + `apps/desktop/cad_workbench/` (Python worker) + `scripts/cad_studio.py` (queue CLI) | Submit tasks through the GUI / manage the queue through CLI |

> Note: `scripts/cad_studio.py` subcommands `doctor/run/status/retry/cancel/...` are **CAD Studio's supporting CLI**, not a fourth user entry point. Any V2 debug/eval commands belong here rather than in a new CLI.

### 1.2 Current module responsibilities against V2 concepts

| V2 concept | Current implementation | Maturity |
|---|---|---|
| Skill (knowledge/SOP/open rules) | `SKILL.md`, `SUBSKILLS.md`, `subskills/*`, `references/*` | Strong |
| MCP (protocol) | `mcp-server/server.py` (approximately 60 allowlisted, serialized tools) | Strong |
| Capability Registry | `capabilities.yaml` + `scripts/capabilities.py` | **Strong: sole source of truth exists** |
| Backend Router | `scripts/capabilities.py::resolve_operation_backend` + `backend_router.py` | **Strong: already exists** |
| Execution Core | **No separate module**; logic distributed across `queue_worker.py` / `sw_review.py` / `reviewer_gate.py` | **Missing: V2 target** |
| Worker | `queue_worker.py` (lease/heartbeat/cancel/stale/quarantine) | Strong |
| Reviewer | `sw_review.py` (CAD geometry) + `reviewer_gate.py` (file facts) + DFM/Routing/drawing evidence | Strong |
| Artifact Ledger | `artifact_ledger.py` (SHA-256, producedThisRun) | Strong |
| Trace | `queue_worker.py::append_event` (job-level JSONL) + stdout/stderr logs | Partial: job-level, no unified run/step model |
| Golden Workflow Eval | `golden-workflows.yaml` (static validation only, no execution benchmark) | **Missing: V2 target** |

---

## 2. Actual call chains

### 2.1 Skill chain (Agent executes scripts directly)

```
LLM Agent (Codex/Claude/OpenClaw)
  └─ Read SKILL.md / SUBSKILLS.md / subskills/*/SKILL.md (SOP and routing)
       ├─ python scripts/sw_preflight.py (dependency/SolidWorks gates, including user-authorized installation)
       ├─ python scripts/backend_router.py --operation ... (read-only backend selection)
       ├─ python scripts/sw_capability_probe.py (capability/type-library probing)
       └─ Execute scripts/sw_*.py (sw_connect / sw_part / sw_assembly / sw_export / sw_motion ...)
            └─ sw_review.run_review() (multiview previews + review_report.json + geometry/B-Rep evidence)
                 └─ Capability gap: references/api-lookup.md → official API Help/SDK → alternate backend → minimal implementation → real-machine run → Review → document reusable solution
```

Key point: the **higher-level Agent directly drives** Skill execution without local Runtime interception. Reliability constraints reach Agent behavior mainly through **SKILL.md rules** (self-review, unwrapped API rules, and prohibiting save-success-only reporting). Therefore **Execution Core cannot directly rewrite the Skill path**; Worker / MCP can gradually reuse it as shared infrastructure, while Skill continues using SOP text and `sw_review.py` as Reviewer instructions.

### 2.2 MCP chain (serialized allowlisted tools)

```
Agent → MCP tool call
  └─ server.py @mcp.tool(...) → def solidworks_*/cadstudio_*/design_spec_*
       └─ _run_locked(op, format, load_automation, timeout=300s)
            ├─ _sw_lock.acquire(timeout)   # Global RLock; serialized SolidWorks COM
            ├─ _load_automation_modules()  # Lazy-load sw_*.py
            ├─ _coinitialize()             # COM thread initialization
            └─ op() → scripts/sw_*.py → _result(json|markdown)
                 └─ Exception → _tool_error(structured status/error_type/message/suggestion)
```

Key point: MCP already provides **strict serialization, lock timeouts, structured errors, lazy loading, and `solidworks_recover` modal-dialog diagnosis**. This is the most stable module and V2 explicitly **leaves it unchanged**.

### 2.3 CAD Studio chain (Worker + gates + ledger + review)

```
UI/CLI → Write Job JSON to the queue directory
  └─ queue_worker.process_queue
       ├─ recover_stale_jobs()                 # Expired-lease recovery / cancellation / invalid-job quarantine
       ├─ acquire_lock() (file lock + lease)   # Cross-process serialization and claiming
       └─ process_job()
            ├─ _capability_block_reasons()      # capabilities.yaml capability gates
            ├─ require_policy_approval()        # Policy Gate: human approval for risky actions
            ├─ mark_job_claimed() → running → heartbeat/lease/cancel
            ├─ Handler dispatch: mock | dfm_review | codex_task | agent_task
            │    └─ run_agent_job()
            │         ├─ engineering_orchestrator (stage DAG planning + RetryPolicy)
            │         ├─ knowledge_retrieval (local RAG)
            │         └─ Subprocess Agent CLI + heartbeat/lease renewal/timeout/cancellation
            ├─ write_artifact_ledger()           # Delivery facts + SHA-256 + producedThisRun
            └─ write_reviewer_gate()             # File-level review
                 └─ Terminal state: passed / review_required / failed / blocked / cancelled
  └─ write_worker_health()
```

Key point: **CAD Studio Worker already functions as an Execution Runtime**, with queue, policy gate, capability gate, ledger, reviewer gate, heartbeat, stale recovery, and JSONL events. V2 Execution Core should unify the **handler → verification → recovery decision abstraction** within this chain rather than replace Queue/Worker/Ledger.

---

## 3. Existing reusable capabilities

### 3.1 Retry (distributed, not unified)

| Location | Mechanism |
|---|---|
| `scripts/sw_macro_guard.py` | Retry failed VBA macro validation 1–2 times, with local templates as fallback (cube/cylinder/extrusion/sketch) |
| `scripts/sw_assembly.py::add_component` | `AddComponent4` failure → retry with `AddComponent5` (Chinese-language SW2024) |
| `scripts/sw_connect.py` / `sw_part.py` | Fallback between English and localized plane names |
| `queue_worker.py` | `QUEUE_WRITE_RETRIES=24` atomic-file-replacement backoff for Windows file locks |
| `engineering_orchestrator.py::RetryPolicy` | Stage-level `max_attempts/strategy/retryable_failures/fallback` (**planning layer, not execution layer**) |

Conclusion: retry concepts exist, but **execution-layer retries are not driven by structured error categories**. V2 Recovery Engine should unify classification → decision, not add another `try/except/retry 3`.

### 3.2 Review / Verification (strong, complementary layers)

- **CAD geometry**: `scripts/sw_review.py` — `run_review` / `evaluate_review_report` / `collect_geometry_measurements` / `validate_hole_positions` / `inspect_pdf_text_layout` / `review_drawing_layout`; outputs `pass/warn/fail` + `manual_review_required` + `retryable`.
- **File facts**: `reviewer_gate.py::evaluate_ledger` — existence/nonzero size/SHA-256/format markers (STEP/STL/DXF/PDF/DWG headers) + specification consistency (three overall dimensions, hole diameter).
- **Domain evidence**: `dfm_review.py`, `routing_review.py`, `sw_drawing_review.py`, FEA evidence, and drawing subskill `drawing_review.py`.

Conclusion: **Reviewer is already strong and must not be rebuilt.** Execution Core's Verification Adapter should only invoke existing review, interpret results, and decide state.

### 3.3 Routing (strong, existing sole source of truth)

`scripts/capabilities.py` already provides `load_capabilities`, `capability_index`, `backend_index`, `operation_route_index`, `resolve_operation_backend`, `capability_level`, `unattended_allowed`, `capability_snapshot`, and `backend_route_snapshot`.

`resolve_operation_backend` implements semantic filtering (automation_equivalent/exact_native...), version blockers (`KNOWN_HOST_REVISION_BLOCKER`), add-in/license requirements (`MISSING_RUNTIME_REQUIREMENT`), candidate priorities, and `unavailable` when no compatible backend exists.

Conclusion: **Backend Router is complete.** `scripts/core/capability.py` may only be an Adapter/Facade and must never duplicate its logic.

### 3.4 Trace / Logs (existing job-level JSONL)

`queue_worker.py` already has:
- `append_event()` → `queue/events/{job_id}.jsonl`, with events such as `run.claimed` / `step.started` / `run.heartbeat` / `run.blocked` / `run.failed` / `run.passed` / `policy.approval_required` / `artifact.ledger_written` / `review.gate_completed`.
- `logs/{job_id}.stdout.log` / `.stderr.log`.

Conclusion: JSONL events exist but are **job-level, without a unified `run_id/trace_id/step_id/parent_step_id` model**; their documented responsibility boundary with Artifact Ledger is not fixed. V2 Trace should reuse the existing `queue/` directory and append-only JSONL semantics, adding a unified step dimension.

### 3.5 Queue State / Worker Health (strong)

`queue_worker.py`: atomic `read_job/write_job`, `acquire_lock/release_lock` (OS file lock + lease), `recover_stale_jobs`, `quarantine_bad_job`, `mark_job_claimed`, `refresh_job_heartbeat`, `request_cancel`, cancellation markers, and `watch_queue`.
`worker_health.py`: `write_worker_health`, `count_jobs`, `health_level` (healthy/attention/warning/error).

Job terminal states: `passed / review_required / failed / cancelled / blocked`; non-executable state: `approval_required`.

Conclusion: **Queue and Worker are stable and indispensable.** Execution Core does not replace them.

### 3.6 Artifact Ledger (strong)

`artifact_ledger.py`: `sha256_file`, `collect_artifact_paths`, `describe_artifact` (exists/size/sha256/**producedThisRun** via baseline snapshot), `build_artifact_ledger`, `write_artifact_ledger`.

Conclusion: **Artifact Ledger = delivery facts**, already complete. Trace must not duplicate it.

### 3.7 Error Handling (weak, no structured categories)

Current state: `sw_preflight` has `DependencyInstallDeclined`/`SolidWorksNotInstalledError`; MCP has structured `_tool_error` payloads; `queue_worker` has `JobCancelled`/`JobBlocked` and fallback `except Exception → failed`.

Missing: **no `TRANSIENT/INVALID_ARGUMENT/ENVIRONMENT_MISSING/TOOL_UNAVAILABLE/BACKEND_UNAVAILABLE/VERIFICATION_FAILED/USER_ACTION_REQUIRED/POLICY_BLOCKED/CAPABILITY_GAP/FATAL` classification**, nor a corresponding unified `RecoveryDecision`.

### 3.8 Policy Gate (strong)

`agent_contracts.py`: `DANGEROUS_CAPABILITIES`, `policy_reasons`, `require_policy_approval`, and `is_policy_approved` (rechecks approval scope; changed reasons trigger interception again).

Conclusion: Policy Gate is authoritative. Execution Core's `POLICY_BLOCKED` category must respect it; **Runtime cannot bypass it**.

### 3.9 Open Capability Gap mechanism (present in Skill, absent in code)

Current state: **entirely in SKILL.md / reference prose**:
- SKILL.md unwrapped API rules: insufficient capability → `references/api-lookup.md` → official API Help / local SDK → alternate backend via `references/language-backend-routing.md` → minimal implementation → real-machine execution → `sw_review.py` → record a reusable solution.
- `references/api-lookup.md` supplies verification templates, minimal validation-script requirements, and documentation rules.

Missing: **no structured `CAPABILITY_GAP` return value**. `resolve_operation_backend` returns `blocked/UNKNOWN_OPERATION_ROUTE` or `unavailable/NO_COMPATIBLE_BACKEND_AVAILABLE`, which are similar but do not explicitly mean "capability gap; return to the higher-level Agent for resolution".

---

## 4. Current responsibilities of capabilities.yaml (sole source of truth)

`capabilities.yaml` (`schema_version: 1.0`) has **four responsibilities**:

1. **Capability maturity manifest** (`capabilities[]`, 29 entries): `id/level/backends/verified_versions/dependencies/limitations/allowed_modes`, sometimes `skills`/`mcp_tools`. level ∈ {verified, pilot, reference_only, not_implemented}.
2. **Backend catalog** (`backend_catalog`, 10 entries): `language/runtime/suitable_for/limitations`.
3. **Atomic operation routes** (`operation_routes`, 14 entries): `id/capability_ids/candidates[{backend,semantics,priority}]/review_required/blocked_revisions/requires/notes/blocked_reason`.
4. **Version matrix facts** (`verified_versions.solidworks/autocad`).

**Key conclusion: `capabilities.yaml` is already the sole capability source of truth, combining capability gates, backend routing, and the version matrix.** V2 must not introduce duplicate configurations such as `tool_registry.yaml`. Extensions may add only **optional** fields (`risk_level / review_required / preferred_backend / fallback_backends / retry_policy / timeout / side_effects`), and `scripts/capabilities.py::load_capabilities` must validate missing fields backward-compatibly.

---

## 5. Duplication and overengineering risks

### 5.1 Existing duplication (V2 must not add more)

1. **Duplicate capability tables**: `engineering_orchestrator.py::CAPABILITIES` embeds a capability mapping (`CapabilityLevel`/skills/mcp_tools) overlapping `capabilities.yaml`. This is historical; **V2 will not refactor it**, but new code must not add a third table.
2. **`resolve_operation_backend` already routes backends**: reimplementing backend selection would duplicate existing work.

### 5.2 Duplication V2 must avoid

1. Another `tool_registry.yaml / runtime_capabilities.yaml / agent_capabilities.json`.
2. Another Reviewer (`sw_review.py` + `reviewer_gate.py` are sufficient).
3. Another Artifact Ledger (Trace records process history, not delivery facts).
4. Another Fake/Mock system (`tests/fakes.py` already provides unified COM substitutes; Eval should reuse or build alongside it).
5. Another Golden Workflow definition (`golden-workflows.yaml` exists; only the execution benchmark is missing).

### 5.3 Overengineering risks

1. **General Agent Framework**: nested Planner/Executor/Reviewer/Manager/Supervisor agents. Higher-level Agents already plan; Execution Core should only Execute/Observe/Verify/Recover/Trace.
2. **Complex state machines**: lightweight Enums suffice for RunStatus/StepStatus; do not build DAG state machines/event sourcing.
3. **Separate Trace Server / Runtime daemon**: Trace appends JSONL into existing `queue/`; never start another service.
4. **Runtime networking**: initial V2 does no Web/API Discovery; return capability gaps to the higher-level Agent.
5. **Wrapping all MCP tools again**: 60+ tools, COM locks, and Pydantic schemas are stable. Gradually reuse Execution Core underneath them without rewriting the layer above.
6. **Terminology proliferation**: use Execution Core consistently, without interchangeable Runtime Engine / Orchestrator / Workflow Engine / Agent Engine labels.

---

## 6. Minimal V2 change proposal

### 6.1 New internal modules (`scripts/core/`, not a user entry point)

```
scripts/core/
├── __init__.py
├── state.py        # Lightweight states: JSON-serializable, versioned
├── capability.py   # Adapter/Facade reusing scripts/capabilities.py + capabilities.yaml
├── trace.py        # Append-only JSONL Trace reusing the queue directory
├── recovery.py     # ErrorKind categories + RecoveryDecision mapping
└── execution.py    # Execution Core facade: Execute → Observe → Verify → Recover → Trace
```

`sync_bundled_skill.py` synchronizes the entire `scripts/` directory, so new `scripts/core/` modules enter the desktop bundle automatically without packaging-script changes.

### 6.2 Module details

**`state.py`**
- `RunStatus`: CREATED / RUNNING / VERIFYING / RETRYING / BLOCKED / FAILED / COMPLETED
- `StepStatus`: PENDING / RUNNING / SUCCESS / FAILED / VERIFYING / RETRYING / BLOCKED
- `RunContext` (run_id/trace_id/goal/status/started_at/finished_at/current_step/steps/artifacts/evidence/errors/retry_count/metadata)
- `StepRecord` (step_id/parent_step_id/tool_name/capability_id/backend/status/started_at/finished_at/duration_ms/arguments_summary/result_summary/error_code/retryable/artifacts/evidence/verification)
- `ExecutionResult` / `VerificationResult` / `RecoveryDecision`
- Constraints: JSON-serializable; versioned schema; **not tightly coupled to CAD Studio Queue Schema**; reusable by Worker/MCP/CLI; **do not duplicate existing Job objects**; store no API keys, complete prompts, secrets, or unnecessary absolute paths.

**`capability.py` (Facade)**
- Provide `get_capability` / `get_operation_route` / `resolve_backend` / `requires_review` / `get_capability_status` / `get_backend_candidates`.
- Delegate everything to `scripts/capabilities.py`, with no duplicated logic.

**`trace.py`**
- Append JSONL events: `run.created / step.started / tool.called / tool.succeeded / tool.failed / verification.started / verification.passed / verification.failed / recovery.retry / recovery.backend_fallback / capability.gap / run.blocked / run.failed / run.completed`.
- Reuse the `queue/` runtime directory, preferably `queue/events/` or a new `queue/trace/` chosen in Phase 2; prefer events to avoid another concept. **Do not write to the repository root**.

**`recovery.py`**
- `ErrorKind`: TRANSIENT / INVALID_ARGUMENT / ENVIRONMENT_MISSING / TOOL_UNAVAILABLE / BACKEND_UNAVAILABLE / VERIFICATION_FAILED / USER_ACTION_REQUIRED / POLICY_BLOCKED / CAPABILITY_GAP / FATAL
- `RecoveryDecision`: RETRY / FALLBACK_BACKEND / REPLAN_REQUIRED / USER_ACTION_REQUIRED / BLOCK / FAIL
- Rules: TRANSIENT→bounded retry; INVALID_ARGUMENT→higher-level Agent; BACKEND_UNAVAILABLE→backend_router fallback; ENVIRONMENT_MISSING→legal fallback if available, otherwise blocked; VERIFICATION_FAILED→prohibit success, repair/replan; USER_ACTION_REQUIRED→blocked; POLICY_BLOCKED→respect Policy Gate without bypass; FATAL→failed.
- Retries must be bounded, traceable, testable, and protected against infinite loops.

**`execution.py` (core gate)**
- Establish Tool Success != Task Success: capabilities with `requires_review` must Execute→Verification→PASS→COMPLETED. Verification FAIL prohibits COMPLETED and must lead to Recovery/Replan/Blocked/Failed.
- Handle multi-step execution, unified Trace, and state decisions only; do not build a complex Planner.

### 6.3 Golden Workflow Eval (`tests/evals/`)

- Reuse `golden-workflows.yaml`, preserving `target_first_pass_rate` compatibility; optionally add `must_review/max_retries/max_tool_calls/expected_capabilities/required_artifacts`.
- Three test categories: Happy Path / Failure Path (Tool success→missing Artifact→Verification Fail→Completed prohibited) / Recovery Path (Primary Backend Fail→Fallback→Success→Verification Pass), plus Capability Gap.
- Metrics: Task Success Rate / First Pass Success Rate / Retry Rate / Recovery Success Rate / **False Completion Rate** (execution reports success while Verifier reports failure) / Average Tool Calls / Average Duration.
- Output `eval_report.json` + `eval_report.md`.
- CI requires no real SolidWorks; use Fake Backend / Mock Tool / Mock Reviewer, reusing or building alongside `tests/fakes.py`.

---

## 7. Planned file changes

| File | Change | Phase |
|---|---|---|
| `docs/architecture/v2-audit.md` | This new audit report | Phase 1 ✅ |
| `scripts/core/__init__.py` | New | Phase 2 |
| `scripts/core/state.py` | New state model | Phase 2 |
| `scripts/core/capability.py` | New Facade | Phase 2 |
| `scripts/core/trace.py` | New JSONL Trace | Phase 2 |
| `scripts/core/recovery.py` | New error classification and recovery decisions | Phase 4 |
| `scripts/core/execution.py` | New Execution Core facade | Phase 3–4 |
| `scripts/core/verification.py` if separate, otherwise within execution.py | Verification Adapter reusing sw_review + reviewer_gate | Phase 3 |
| `tests/test_core_state.py` and others | Unit tests for state transitions/retry limits/fallback/POLICY_BLOCKED/CAPABILITY_GAP/Trace JSONL | Phase 2–4 |
| `tests/evals/golden_workflow_eval.py` | Golden Workflow Eval + eval_report output | Phase 6 |
| `golden-workflows.yaml` | Append **optional** fields only (must_review/max_retries/...); do not change old workflows | Phase 6 |
| `apps/desktop/cad_workbench/queue_worker.py` | Minimal integration of Execution Context + Verification + Recovery Decision between handler and ledger/reviewer; **no rewrite** | Phase 5 |
| `scripts/cad_studio.py` | Optional `inspect-trace` / `eval` debug subcommands; omit if unnecessary | Phase 8 |
| `capabilities.yaml` | Optionally append risk_level/review_required/... fields; defer by default | Phase 2 optional |
| `docs/architecture/execution-core.md` | New technical documentation | Phase 8 |
| `README.md` | One user-facing sentence: V2 adds internal reliable execution, automatic verification, and failure recovery without another service | Phase 8 |

---

## 8. Modules explicitly left unchanged

| Module | Reason |
|---|---|
| `mcp-server/server.py` | 60+ tools, Pydantic schemas, `_sw_lock` serialization, lock timeouts, `_coinitialize`, `_run_locked`, and `solidworks_recover` are stable; SolidWorks COM must remain serialized, with no second lock |
| `scripts/sw_*.py` COM wrappers: sw_connect/sw_part/sw_assembly/sw_export/sw_motion/sw_drawing/sw_hole_features/sw_measure/sw_edge_select/sw_document_data/sw_delivery/sw_appearance/sw_session/sw_macro_guard... | Stable capabilities with real-machine regression; reuse without rewriting |
| `scripts/capabilities.py` + `scripts/backend_router.py` | Complete routing logic, reused as source of truth |
| `apps/desktop/cad_workbench/reviewer_gate.py` | Reviewer Gate is complete |
| `apps/desktop/cad_workbench/artifact_ledger.py` | Artifact Ledger is complete |
| `apps/desktop/cad_workbench/worker_health.py` | Worker Health is complete |
| `apps/desktop/cad_workbench/agent_contracts.py` | Policy Gate is authoritative |
| `apps/desktop/cad_workbench/agent_providers.py` | Stable Provider Adapter |
| `apps/desktop/cad_workbench/knowledge_retrieval.py` | Stable RAG |
| `apps/desktop/cad_workbench/engineering_orchestrator.py` | Stable stage DAG; embedded capability table is historical and not refactored in V2 |
| `apps/workbench-ui/` frontend | User interface unchanged |
| `SKILL.md` / `SUBSKILLS.md` / all `subskills/*` | User SOPs unchanged; retain open-capability mechanism prose |
| `install.js` / `manifest.json` / `package.json` / `setup.py` / `pyproject.toml` / registry scripts | Installation and packaging unchanged |
| `scripts/sync_bundled_skill.py` | Directory-based `scripts/` sync automatically includes `scripts/core/`; no changes needed |

> `queue_worker.py` is the **only** runtime file planned for minimal modification: integrate Execution Core at the existing handler→ledger→reviewer boundary without rewriting Queue/Lease/Heartbeat/Policy Gate logic.

---

## 9. Required compatibility constraints throughout V2

1. No new user entry point or service: runtime/executor/orchestrator/trace server/eval server are prohibited.
2. `capabilities.yaml` remains the sole capability source of truth; only optional fields may be appended.
3. No breaking MCP Tool Name / Input Schema changes or SolidWorks COM serialization-lock changes.
4. Runtime cannot bypass authoritative Policy Gate / Approval.
5. Worker Health / Heartbeat / Stale Recovery / Artifact Ledger continue working.
6. Runtime Trace/Log/Artifact data is written only into existing runtime directories such as `queue/ logs/ artifacts/`, not the source repository root.
7. CI requires no real SolidWorks; real-machine regression remains separately self-hosted.
8. The end-user flow remains install → talk to AI → receive trustworthy results.

---

## 10. Core conclusions

- **The project is already partly an Execution Runtime**: queue, policy gate, capability gate, backend router, reviewer gate, artifact ledger, JSONL events, stale recovery, and heartbeat are all present.
- **V2's minimum new core is five files**: `state.py` / `capability.py` (facade) / `trace.py` / `recovery.py` / `execution.py`, plus a thin verification adapter and Golden Workflow Eval.
- **Engineering value** comes from consolidating four reliability ideas currently distributed, implicit, and prompt-dependent—Tool Success ≠ Task Success, structured error classification→recovery decisions, unified run/step Trace, and structured capability-gap returns—into a **reusable, unit-testable, measurable** lightweight layer.
- **The largest risk is excess implementation**, not inability to implement. Rebuilding capability tables, Reviewers, Ledgers, multi-agent systems, locks, or services turns an internal reliability upgrade into overengineering. Every phase must check duplication, compatibility, and added user complexity.

---

## 11. Decisions required before Phase 2

1. **Trace storage**: reuse `queue/events/{job_id}.jsonl` with step_id added, or introduce `queue/trace/{run_id}.jsonl`? Recommendation: **reuse `queue/events/`**, adding `schema_version` and `run_id/trace_id/step_id/parent_step_id` to events to avoid another top-level concept.
2. **Separate Verification Adapter in `scripts/core/verification.py`?** Recommendation: a separate single-responsibility module reusing sw_review + reviewer_gate; integration into execution.py is also possible. Default to separate.
3. **Phase 5 Worker integration depth**: integrate `queue_worker.process_job` now, or establish `scripts/core/` first and defer Worker integration until regression stabilizes? Recommendation: **minimal integration in sequence at Phase 5**, wrapping only the handler→verification→recovery boundary.
4. **Optional capabilities.yaml fields**: append `risk_level/review_required/...` now, or leave YAML unchanged and let the facade read existing fields? Recommendation: **leave YAML unchanged by default in Phase 2**, reuse existing fields first, and add optional ones only when necessary.

After these four decisions, proceed to Phase 2 (State + Capability Adapter + Trace).
