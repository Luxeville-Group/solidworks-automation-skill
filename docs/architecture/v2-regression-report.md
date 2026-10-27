# V2 Regression Report & Reliability Baseline

> This document preserves Phase 7/7.5 history. Since 2026-10-08, baseline v3 uses nominal 10/10 and blocks warning pending human review. Current verification results are in [`scheme-b-reliability.md`](scheme-b-reliability.md).

> Stage: Phase 7 (Full Regression + Baseline Freeze) + Phase 7.5 (Evaluation Semantics Correction)
> Conclusion: V2 caused no regressions; Eval semantics were corrected to separate Nominal/Robustness/Safety, and the corrected baseline was frozen.

## 1. V2 architecture version

- Execution Core: `scripts/core/` (state / capability / trace / verification / recovery / execution)
- Internal execution chain: `State → Capability Facade → Trace → Verification Adapter → Recovery Decision → Execution Core`
- Three user entry points remain unchanged: Skill / MCP / CAD Studio
- Across V2, only one existing file changed: `apps/desktop/cad_workbench/queue_worker.py` (+58 / −1)

## 2. Regression Matrix

| Subsystem | Tests | Result | Environment |
|---|---|---|---|
| Core State / Capability / Trace | 36 | PASS | CI-safe |
| Core Verification / Recovery / Execution | 62 | PASS | CI-safe |
| Golden Eval (metrics / runner / baseline) | 27 | PASS | CI-safe |
| Worker / Reviewer / Ledger / Policy / Health / Orchestrator | 94 | PASS | CI-safe |
| Other unit tests (sw/mcp/design/dfm/routing/fea/headless/drawing/subskills/…) | 521 | PASS | CI-safe |
| Release Check (embedded Skill packaging) | 1 | SKIP | Run `sync_bundled_skill.py` first |
| **pytest total** | **740 passed / 1 skipped** | **0 failed** | CI-safe |
| SolidWorks real-machine regression (`solidworks_*_regression.py`) | — | NOT RUN | Windows + SolidWorks |
| AutoCAD real-machine regression (`autocad_*_regression.py`) | — | NOT RUN | Windows + AutoCAD |
| CAD Studio weekly regression (`cad_studio_weekly_regression.py`) | — | NOT RUN | Windows + CAD |
| CalculiX external solver (`calculix_*_regression.py`) | — | NOT RUN | CalculiX |

> Real-machine/external-solver regression runs separately through `.github/workflows/windows-cad-regression.yml` (self-hosted Windows + CAD).

## 3. Backward Compatibility

| Item | Result |
|---|---|
| A. Skill (SKILL.md usage) | Unmodified, entirely unchanged |
| B. MCP (Tool Name / Input Schema / startup) | Unmodified, entirely unchanged |
| C. CLI (`cad_studio.py` commands) | Unmodified, entirely unchanged |
| D. CAD Studio (old Queue Jobs / events / Worker status semantics) | Old Jobs work without sidecar fields; old events remain readable without run_id/step_id; Worker terminal-state semantics remain intact |
| E. capabilities.yaml | Unchanged sole capability source of truth |
| F. golden-workflows.yaml | Unchanged; old format remains compatible |

## 4. Official Eval Metrics (corrected Phase 7.5 semantics)

`python tests/evals/runner.py` (complete 37-scenario set with four metric groups):

### Nominal Reliability (11 nominal scenarios)

| Metric | Value |
|---|---|
| Nominal Scenarios | 11 |
| Nominal Task Success Rate | 100.0% |
| Nominal First Pass Success Rate | 100.0% |
| Target First Pass | 90% |
| **Target Status** | **PASS** |
| Average Tool Calls | 1.0 |
| Average Duration | 0.0 ms |

### Robustness (26 robustness scenarios)

| Metric | Value |
|---|---|
| Robustness Scenarios | 26 |
| Expected Outcome Accuracy | 100.0% |
| Recovery Success Rate | 100.0% |
| Failure Detection Rate | 100.0% |
| Policy Block Accuracy | 100.0% |
| Capability Gap Detection | 100.0% |
| Backend Fallback Decision Accuracy | 100.0% |
| Reviewer Block Detection | 100.0% |
| Retry Exhaustion Accuracy | 100.0% |

### Safety

| Metric | Value |
|---|---|
| Raw Handler False-Positive Incidence | 33.3% (deliberately injected by fault-injection scenarios) |
| False-Completion Detection Rate | 100.0% |
| **Escaped False Completion Rate** | **0.0%** |

### Overall Diagnostic (not used for the target)

| Metric | Value |
|---|---|
| Overall Scenario Count | 37 |
| Overall Raw Task Completion Rate | 59.5% (diagnostic only) |
| Overall Average Tool Calls | 1.27 |

## 5. Reliability Baseline (corrected Phase 7.5 semantics)

Frozen in `tests/evals/baseline.json` (`schema_version: 2.0`, `baseline_version: 2`):

- `nominal_metrics`: 11 scenarios / task_success 1.0 / first_pass 1.0
- `robustness_metrics`: 26 scenarios / expected_outcome_accuracy 1.0 / recovery 1.0 / detection 1.0
- `safety_metrics`: raw_false_positive 0.3333 / detection 1.0 / **escaped 0.0**
- `overall_diagnostic_metrics`: 37 scenarios / raw completion 0.5946

**Release Guard** (`tests/test_eval_baseline.py`):
- `nominal_first_pass_success_rate >= target_first_pass_rate` (1.0 ≥ 0.90 ✅)
- `escaped_false_completion_rate == 0` ✅
- `expected_outcome_accuracy` does not degrade ✅

## 6. CI-safe / live-test boundaries

- **CI-safe**: all pytest tests (Windows CI + pywin32/comtypes; no real CAD binaries required).
- **CAD-live**: SolidWorks / AutoCAD / CAD Studio real-machine regression scripts (not named `test_*.py`, excluded from pytest collection).
- **external-solver**: CalculiX regression scripts.

## 7. Known limitations and metric interpretation

- Eval is a **Deterministic Execution Reliability Benchmark** (Fake Handler/Reviewer),
  **not** a real-user success rate, all-scenario SolidWorks success rate, measure of Codex intelligence, or production SLA.
- Duration ≈ 0 ms because fake handlers run instantly; meaningful timing requires Live Agent Eval.
- `Overall Raw Task Completion Rate` (59.5%) is diagnostic only and not compared with the target.
- **Phase 7.5 semantics correction**: pooling nominal and fault-injection denominators produced:
  - 29.7% first-pass (compared with 90%, falsely reporting BELOW_TARGET);
  - 33.3% false completion (actually Verification correctly intercepting 11 injected false-completion candidates, not leakage).
  Corrected nominal first-pass = 100% (PASS), escaped false completion = 0%.
- `test_release_check` skip: first run `python scripts/sync_bundled_skill.py`.

## 8. Issues found

**No production-code bug.** Phase 7.5 found and corrected an **Eval metric-semantics issue** (pooled statistics),
resolved through classification, grouped metrics, and three-layer false-completion definitions, without changing production execution code.

## 9. Production-code changes

Across V2, only one existing file changed: `apps/desktop/cad_workbench/queue_worker.py` (+58/−1, Phase 5
minimal integration). Phases 6–7.5 changed no production code, only `tests/evals/*`, `tests/test_eval_*`, and docs.

Core module line counts (bounded, single responsibility): state 373 / capability 125 / trace 166 / verification 295 /
recovery 432 / execution 255. Worker / Planner / Reviewer / Router logic was not absorbed.

## 10. Readiness for V2 Documentation Freeze

**Ready (pending confirmation).** V2 completed: architecture audit → state/capability/Trace → verification adapter → recovery decisions →
execution orchestration + minimal Worker integration → reliability Eval → regression + baseline freeze → Eval semantics correction.
Next is Phase 8 (Documentation Freeze: add `docs/architecture/execution-core.md` +
a one-sentence README explanation).
