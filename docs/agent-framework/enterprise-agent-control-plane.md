# CAD Studio Enterprise Agent Control Plane

## Positioning

CAD Studio is an Agent control plane for mechanical engineers, rather than merely embedding a language model in CAD software:

```text
Graphical configuration -> Enterprise task contract -> Codex execution -> Skill/toolchain -> Review gate -> Delivery writeback
```

Codex remains the final executor, and the `solidworks-automation` skill is the core capability package. The interface converts user intent into auditable, reusable, replayable task specifications.

## Reference approaches

From educational/framework projects such as `datawhalechina/hello-agents`:

- Basic Agent abstractions: roles, tools, memory, context, protocols, and evaluation.
- Progression from single-turn prompts to reusable workflows.
- Case-driven development connecting framework capabilities to real tasks.

From more complete frameworks such as Hermes Agent:

- Long-running workers.
- Separate Agent Profile / Skill / Memory layers.
- Multi-Agent delegation and review.
- Gateways, auditing, permissions, and reversible execution.

This project adapts these concepts to the CAD/Skills domain rather than copying a general-purpose Agent framework wholesale.

## Module boundaries

- UI: Collect configuration; display the queue, prompt preview, and results.
- Queue: Persist tasks as JSON for offline recovery.
- Agent Contract: Compile Agent Profile, Policy, Prompt, and Output Schema.
- Worker: Monitor the queue and dispatch mock / Codex / CAD handlers.
- Codex Executor: Invoke `codex exec`, require skill loading, and produce structured results.
- Reviewer Gate: Check actual holes, GB/T drawings, tests, Git state, and deliverables.
- Artifact Store: Store Codex output, CAD files, review reports, and queue logs.

## Implementation status

Implemented:

- Tauri local queue.
- Python worker.
- `executor: "codex"` bridge.
- Codex Bridge UI.
- Agent Profile and prompt compiler.
- Codex final-response JSON schema.
- Versioned task Schema.
- Default `workspace-write` sandbox, workspace allowlist, and fixed output directory.
- JSON queue claim locks, leases, stale-running recovery, and invalid-task quarantine.
- Running heartbeat lease renewal, cancellation semantics, JSONL events, and persisted stdout/stderr logs.
- Policy Gate human approval covering Git push, full-access sandbox, CAD macros, external networks, cross-workspace writes, and file deletion.
- Approval-scope rechecking: the worker intercepts a task again if its risk reasons change after approval.
- Artifact Ledger: successful tasks automatically record deliverable paths, existence, sizes, and SHA-256.
- Worker Control: the desktop can start/stop a local Python worker and display its state and PID.
- Worker Health: workers record health heartbeats, queue statistics, recovery counts, and recent errors.
- Reviewer Gate: produce artifact review reports from the Artifact Ledger and perform lightweight STEP/STL/DXF/PDF/DWG format checks.

Not implemented:

- In-application worker start/stop.
- Live queue log streams.
- Multi-Agent parallel/review scheduling.
- Memory and enterprise permissions.
- Production-grade rollback for real CAD executors.
- HMAC signatures and immutable audit ledgers.

## Minimum enterprise principles

- Every task must have structured JSON.
- Every execution must produce an output file.
- Every Codex call must reference the skill path.
- Every delivery must have verification records.
- Real manufacturing files must pass Reviewer Gate.
- Unspecified engineering options default to `auto_best`: AI selects the best approach and records the rationale and remaining risks.
- Codex execution must be explicitly enabled; silent execution by default is prohibited.
- `danger-full-access` requires both task approval and the worker's `--codex-full-access` switch; it must not be the default.
- Frontend task JSON is untrusted; Policy Gate must be enforced at the worker/control-plane layer.

## Policy Gate

The current Policy Gate prevents risky actions from being executed silently with one UI click. After a Codex task enters the worker, it checks the following before calling `codex exec`:

- `policy.approval == "manual-required"`.
- `policy.requirePush == true` or UI configuration `commitAndPush == true`.
- `policy.sandbox == "danger-full-access"`.
- `capabilities` contains `git_push`, `full_access`, `cad_macro`, `external_network`, `cross_workspace`, or `delete_files`.

A match moves the task to `approval_required`; the worker writes `approvalReasons` and a `policy.approval_required` event. Desktop approval writes `approvedAt`, `approvedBy`, and `approvedPolicyReasons`, then restores `queued`. The worker recalculates approval reasons and continues only if they match the approved reasons.

## Artifact Ledger

Artifact Ledger is the foundation for Reviewer Gate. After task success, the worker combines `result.outputPath`, `result.outputs`, `result.artifacts`, and task-level `artifacts` into `queue/ledgers/{job_id}.ledger.json`, recording:

- Deliverable kind/path.
- Whether each file exists and whether it is a directory.
- File size and SHA-256.
- Execution result messages and verification summaries.

The Ledger records facts and does not replace manufacturing-level acceptance. Before writing `passed`, real CAD handlers must still verify that P0 files such as STEP/STL/DWG/PDF actually exist, open, and are manufacturable.

## Worker Health

The worker writes `queue/worker_health.json` with the heartbeat, PID, queue state statistics, count processed this run, stale-running recovery count, and recent errors. Reading this file lets the desktop distinguish process state from queue health: a live process does not mean healthy tasks, and failures or pending approvals require clear notices.

## Reviewer Gate

Reviewer Gate currently checks artifact facts and lightweight format markers, reporting to `queue/reviews/{job_id}.review.json`. It checks declaration, existence, nonzero size, and SHA-256, plus file headers or structural markers for STEP/STP, STL, DXF, PDF, and DWG. SLDPRT is proprietary; current handling records a warning, with SolidWorks open-and-review integration planned.

## Near-term roadmap

1. Queue Store: Add an event timeline UI, running-task retry policies, and queue health state.
2. Reviewer Gate: Add actual SolidWorks/AutoCAD open checks, drawing dimension-chain checks, and verification of real holes for 3D printing.
3. Worker Health: Persist crash causes; add queue health scores and a UI timeline.
4. UI: Replace Prompt Preview with execution plans, gates, and affected scope; move prompts to advanced details.
5. Multi-Agent: Add Planner/Executor/Reviewer stages, prioritizing traceability and acceptance over unnecessary multiprocess complexity.
