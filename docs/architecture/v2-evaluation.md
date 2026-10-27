# V2 Evaluation —— Golden Workflow Reliability Eval

## 1. Why Eval is needed

V2 aims to make existing capabilities execute more reliably. Subjective judgment alone is insufficient; it needs a
**repeatable, measurable, CI-compatible** reliability baseline answering:

1. How many normal tasks succeed? (Nominal Task Success Rate)
2. How many normal tasks succeed on the first attempt? (Nominal First Pass Success Rate)
3. Can execution recover after failure? (Recovery Success Rate)
4. Does the system correctly detect injected faults? (Failure Detection / Expected Outcome Accuracy)
5. Does any **false completion escape**, where a tool reports success, Verification fails, but the final task still counts as successful? (Escaped False Completion Rate)

These measurements come from **deterministic Execution Core + Fake Handler/Reviewer** behavior,
independent of model randomness, networking, and real-machine CAD environments.

## 2. What a Golden Workflow is

`golden-workflows.yaml` is the **sole source of truth** for Golden Workflows (`schema_version: 1.0`),
containing `target_first_pass_rate` and 10 workflows. Eval **derives scenarios directly from this file**, without copying
its contents or introducing a second configuration. Existing fields continue to work.

## 3. Scenario categories (benchmark_group)

Eval scenarios must be separated by **measurement population**; intentionally failing scenarios must never share
the normal business scenario denominator. Scenario type determines categories **deterministically**:

| category | scenario types | Purpose |
|---|---|---|
| `nominal` | happy | Normal business tasks; used for first-pass target comparison |
| `recovery` | transient_recovery, backend_fallback | Scripted recovery after failure |
| `fault_injection` | verification_failure, reviewer_blocked, retry_exhausted | Deliberately injected faults to verify detection |
| `guardrail` | warning, policy_block, user_action_required, capability_gap | Verify correct gate/human-review blocking |

## 4. Metric definitions

### Nominal (nominal scenarios only)

| Metric | Definition |
|---|---|
| nominal_task_success_rate | Proportion of nominal scenarios with `terminal == completed` |
| nominal_first_pass_success_rate | Proportion of nominal scenarios that are `completed` in one attempt with no recovery |
| nominal_average_tool_calls / duration | Means within the nominal subset |

`target_first_pass_rate` (0.90) **is compared only with nominal_first_pass_success_rate**.

### Robustness (recovery / fault_injection / guardrail)

| Metric | Definition |
|---|---|
| expected_outcome_accuracy | Proportion with `terminal == expected_terminal_status` (the main Robustness metric) |
| recovery_success_rate | Proportion of recovery scenarios that are `completed` |
| failure_detection_rate | Proportion of fault_injection scenarios with `terminal != completed` (correctly detected injected failures) |
| policy_block_accuracy | Proportion of policy_block scenarios with `terminal == blocked` |
| capability_gap_detection_rate | Proportion of capability_gap scenarios with `terminal == failed` |
| backend_fallback_decision_accuracy | Proportion of backend_fallback scenarios with `terminal == completed` |
| reviewer_block_detection_rate | Proportion of reviewer_blocked scenarios with `terminal == blocked` |
| retry_exhaustion_accuracy | Proportion of retry_exhausted scenarios with `terminal == failed` |

Note: **BLOCKED is the correct outcome for policy blocks, and FAIL/REPLAN is correct for capability gaps**.
These are **correct handling**, not task failures. Robustness therefore uses `expected_outcome_accuracy`
rather than task success.

### Safety (false completion)

| Metric | Definition |
|---|---|
| raw_false_completion_incidence | Handler success with Verification FAIL/BLOCKED / number of Handler successes. **May be high**, because fault injection deliberately creates these cases. |
| false_completion_detection_rate | Injected false-completion candidates correctly intercepted by Verification / all injected false-completion candidates. Target approaches 100%. |
| escaped_false_completion_rate | Proportion where Handler reports success, Verification is FAIL/BLOCKED, and the final result is still `completed`. Target: **0**. |

### Overall (diagnostic; not used for the target)

| Metric | Definition |
|---|---|
| overall_scenario_count | Total scenario count |
| overall_raw_task_completion_rate | Overall proportion with `terminal == completed` (diagnostic only) |

## 5. Precise false-completion definitions (corrected)

Distinguish three layers strictly:

- **Raw false positive** (Handler false positive) = `handler_success AND verification ∈ {FAIL, BLOCKED}`.
  This is the **incidence** of underlying execution producing false-completion candidates. Fault-injection scenarios naturally increase it; it is **not the system's escaped false-completion rate**.
- **Detection rate** = proportion of injected false-completion candidates correctly intercepted by Verification. **High = effective Verification**.
- **Escaped rate** = proportion of false-completion candidates still treated as `completed`. **This is actual false-completion leakage**, with a target of 0.

The old version conflated these into `false_completion_rate` (33.3%), making "Verification correctly intercepted
11 false-completion candidates" look like "the system has 33.3% escaped false completion".

## 6. Problems with the old calculation (why 59.5% / 29.7% / 33.3% mislead)

The old Phase 6 calculation pooled all 37 scenarios (10 happy + 10 verification_failure + 10 transient_recovery
+ 7 cross-cutting cases) **into one denominator** for first-pass and false-completion rates:

- **29.7% first-pass**: 10 happy + one warning succeeded initially, divided by all 37 scenarios, including intentional failures.
  This understates the normal-business first-pass rate, and comparison with a 90% target falsely reported BELOW_TARGET.
- **33.3% false completion**: 10 verification_failure + one reviewer_blocked were **deliberately injected**
  false-completion candidates correctly intercepted by Verification. The old calculation measured incidence rather than leakage;
  actual escaped false completion was **0%**.

Current baseline v3: warning belongs to the human-review guardrail and cannot claim task completion. `nominal_first_pass = 100%` (10/10) → compare with 90% target → **PASS**;
`escaped_false_completion = 0%` → no escaped false completion.
The raw completion ratio across 37 scenarios is 21/37 (56.8%), diagnostic only. Earlier 11/11 and 59.5% figures are historical metrics that counted warning as success.

## 7. Deterministic fixture design

No LLM / Web / real-machine calls. Fake Handlers (`success_handler`/`fail_handler`), Fake Reviewers
(`pass/warn/fail/blocked/crash_reviewer`), a Fake Capability Facade, and
exception types matching `core.recovery._EXCEPTION_KIND` are used. Subsequent recovery outcomes are simulated
with scripted multiple attempts; production Worker automatic retries are unchanged.

## 8. Running Eval

```powershell
python tests/evals/runner.py
```

Outputs `eval_report.json` + `eval_report.md` (default `tests/evals/reports/`, gitignored).

## 9. Reading the report

The report has four sections: Nominal Reliability (normal-business success and target comparison), Robustness (correct handling and
detection), Safety (false-completion incidence/detection/escaped), and Overall Diagnostic (diagnostic only).

- `Nominal First Pass Success Rate` vs `Target` → `PASS/BELOW_TARGET`.
- `Escaped False Completion Rate` → must be 0.
- `Expected Outcome Accuracy` → combined measure of correct Robustness handling.

## 10. What current Eval does not cover

- Real SolidWorks / AutoCAD execution (covered by real-machine regression).
- Real LLM Planning / Tool Calling quality, model comparisons, token costs, or LLM judges.
- Networking / external APIs.

## 11. Extending to future Live Agent Eval

Phase 6/7.5 tests only **Execution Reliability** (deterministic). Future Live Agent Eval can run
real Codex/Claude through the real Skill + Worker, reusing `EvalRecord` / `metrics` /
`EvalReport` and replacing only `run_scenario`'s handler with a real Agent call.
