# Multi-Agent Provider Architecture

## Goal

CAD Studio supports different user environments without binding to one model or CLI. All providers share a CAD task protocol, approval policy, knowledge retrieval, artifact ledger and review gates; differences are confined to command compilation and result parsing.

```text
User task
  -> UnifiedAutomationJob
  -> Policy Gate
  -> Provider Adapter
  -> Codex / Claude Code / Gemini CLI / OpenCode
  -> UnifiedAgentResult
  -> Artifact Ledger
  -> CAD/B-Rep/Motion Reviewer Gate
  -> Local delivery directory
```

## Keep provider states distinct

The interface and logs must distinguish these states:

| State | Evidence | May it be called connected? |
|---|---|---|
| Not installed | CLI entry point missing or `--version` fails | No |
| Installed | `--version` succeeds | No |
| Authentication failed | Official authentication-status command fails | No |
| Authentication pending verification | CLI has no inexpensive authentication-status query | No; verify with the first real task |
| Authentication verified | Official authentication command succeeds | May be described as authenticated |
| Execution verified | A real task returns structured results under the common protocol | May be described as successful execution of that task |

The presence of a CLI, environment variable or provider configuration in CC Switch does not independently prove model requests work. A provider's success claim does not establish the correctness of SolidWorks/AutoCAD artifacts.

## Common task protocol

Use task type `agent_task` and executor `agent`:

```json
{
  "kind": "agent_task",
  "executor": "agent",
  "objective": "Create a mounting plate with counterbores and a semicircular-ended slot",
  "skillPath": "C:/Users/user/.codex/skills/solidworks-automation/SKILL.md",
  "uiConfig": {
    "agentRuntime": {
      "provider": "claude",
      "providerName": "Claude Code",
      "protocol": "claude-print-v1",
      "model": ""
    }
  }
}
```

Legacy `codex_task` and `executor=codex` remain compatibility entry points; the Worker normalizes them to the same execution flow.

## Common result protocol

Every provider must produce these final fields:

```json
{
  "summary": "Work completed in this run",
  "changedFiles": [],
  "verification": [],
  "risks": [],
  "nextSteps": []
}
```

The common result is an agent execution record, not CAD acceptance evidence. Mechanical deliverables still need independent file hashes, B-Rep dimensions, hole/slot positions, previews, Motion results and human-review records.

## Current adapters

| Provider | Protocol ID | Noninteractive entry point | Structured output source |
|---|---|---|---|
| Codex | `codex-exec-v1` | `codex exec` | `--output-schema` + output file |
| Claude Code | `claude-print-v1` | `claude -p` | `--output-format json` + `--json-schema` |
| Gemini CLI | `gemini-headless-v1` | `gemini -p` | JSON response wrapper |
| OpenCode | `opencode-jsonl-v1` | `opencode run` | JSONL text events |

Implementation:

- `apps/desktop/cad_workbench/agent_providers.py`
- `apps/desktop/cad_workbench/queue_worker.py`
- `apps/workbench-ui/src-tauri/src/lib.rs`

## Adding a provider

1. Register a stable ID in `SUPPORTED_PROVIDER_IDS` and the frontend `AgentProviderId`.
2. Use only noninteractive options confirmed in the CLI's official documentation; do not guess flags from memory.
3. Compile the common task into a provider command in `build_provider_command()`.
4. Parse the native wrapper in `parse_provider_result()` and require the common result fields.
5. Add tests for installation, authentication, timeouts, non-JSON output, missing fields and cancellation.
6. Distinguish installation, authentication and execution verification in desktop health checks instead of adding an ambiguous connected Boolean.
7. Run a real minimal probe to verify exit codes, stdout/stderr, cancellation and timeout behavior.

## Observable execution

The software can show plans, public steps, tool calls, approvals, logs, file changes and review results. Do not promise or fabricate hidden model chain-of-thought; users need an auditable execution trace and conversational context they can follow up on.

## Security boundaries

- Provider adapters do not directly expose arbitrary Python, PowerShell or VBA tools.
- Serialize CAD COM calls so multiple agents cannot manipulate one desktop session simultaneously.
- External network access, cloud RAG and dangerous local CAD actions pass through the Policy Gate.
- Never put API keys in task JSON, logs or frontend persistence; record only redacted state or environment-variable names.
- Provider output must pass schema, Artifact Ledger and Reviewer Gate checks before delivery can be declared successful.
