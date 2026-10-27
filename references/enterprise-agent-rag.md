# Enterprise Agents and Mechanical Knowledge Bases

## Target architecture

CAD Studio combines a control plane, deterministic CAD tools, a Reviewer Gate and local-first RAG:

```text
User conversation / UI configuration
  -> Intake / Planner
  -> Local knowledge retrieval (default)
  -> Optional cloud retrieval (explicit enablement + external-network approval)
  -> Codex Executor
  -> Serialized SolidWorks / AutoCAD tools
  -> Artifact Ledger
  -> Reviewer Gate
  -> Human review and continued conversation
```

`apps/desktop/cad_workbench/knowledge_retrieval.py` implements:

- Retrieval from the root `SKILL.md`, `references/` and all subskill reference and knowledge files.
- Token-based retrieval, chunking and Top-K ranking for localized and English text.
- Source path, content SHA-256, score and provider for each passage.
- Automatic injection of retrieved passages into the Worker's enterprise prompt.
- An optional HTTPS cloud RAG connector whose token is read only from an environment variable.

## Data boundaries

1. By default, retrieve only local skill knowledge; do not upload user projects, models, drawings or prompts.
2. Cloud knowledge access requires explicit `external_network` in the task and human approval.
3. Cloud endpoints must use HTTPS. Do not write tokens to task JSON, logs or persisted UI files.
4. The token environment variable is fixed to `CAD_STUDIO_RAG_TOKEN`; tasks cannot name other variables and thereby read and transmit unrelated credentials.
5. Custom local knowledge directories trigger approval for cross-workspace access; direct queue-file writes cannot bypass the gate.
6. Retrieved passages are reference evidence, not replacements for original GB/T, ISO, material handbooks, supplier catalogs or company standards.
7. Knowledge passages must retain `source` and `sha256`; untraceable content cannot establish manufacturing acceptance.

## Task configuration

```json
{
  "uiConfig": {
    "knowledgeBase": {
      "topK": 6,
      "localRoots": ["D:/company-cad-standards"],
      "cloudEnabled": false,
      "endpoint": "https://rag.example.com/retrieve",
      "namespace": "mechanical-engineering",
      "tokenEnv": "CAD_STUDIO_RAG_TOKEN"
    }
  }
}
```

Cloud service response contract:

```json
{
  "chunks": [
    {
      "title": "Bearing housing bore fit",
      "source": "enterprise-standard://bearing/fit-v3",
      "text": "Retrievable original source passage",
      "score": 0.91
    }
  ]
}
```

## Knowledge layers

- `L0 Session facts`: user dimensions, purpose, material, loads, manufacturing method and target software.
- `L1 Project knowledge`: current drawings, parameter tables, BOM, company standards and revision history.
- `L2 Skill knowledge`: repository references, specialist subskills and verified API experience.
- `L3 Organization knowledge`: approved templates, failure cases, process capabilities and supplier constraints.
- `L4 External knowledge`: official APIs, national/industry standards and manufacturer manuals; retain versions and sources.

Retrieval priority is `L0 > L1 > L2 > L3 > L4`. Stop automatic execution on conflicts and submit them to the Reviewer instead of silently selecting a source.

## Gates before cloud deployment

- Tenant namespace isolation and least-privilege tokens.
- Document-level ACLs applied before retrieval, not merely after answer generation.
- Immutable audit records for uploads, deletions and reindexing.
- Client-side redaction of PII, keys, customer drawing watermarks and controlled technical data.
- Source revocation, version rollback, expiry policies and citation-hit statistics.
- Original-source review labels for standard numbers, materials, tolerances and factors of safety.
