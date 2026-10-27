# SolidWorks Automation subskill matrix

The root `solidworks-automation` skill provides connection, document management, modeling APIs, export, review and MCP. Specialist workflows live in `subskills/`, each with its own instructions, metadata, scripts, references and examples. Read the exact scope and capability gates before executing; directory-level status is not a guarantee for every operation.

## Index

| Subskill | Declared status | Purpose | Instructions |
|---|---|---|---|
| `solidworks-vibecad` | experimental | Natural-language requirements → parametric plan, manufacturing checks, execution outline and review gates | [SKILL.md](subskills/solidworks-vibecad/SKILL.md) |
| `solidworks-fillet-chamfer-cnc` | stable | CNC mounting bases, parameter/collision checks, semantic edge selection, bounded dimension fallback, holes/slots and rounded pockets | [SKILL.md](subskills/solidworks-fillet-chamfer-cnc/SKILL.md) |
| `solidworks-threaded-holes` | stable | M3-M12 threaded/tap-drill holes, mouth chamfers, thread properties and STEP | [SKILL.md](subskills/solidworks-threaded-holes/SKILL.md) |
| `solidworks-engineering-drawing` | pilot | GB/T first-angle drawings, dimension chains, hole tables, BOM, PDF/BMP evidence and manufacturing-delivery review | [SKILL.md](subskills/solidworks-engineering-drawing/SKILL.md) |
| `autocad-automation` | stable, with per-backend restrictions | 2D DWG/DXF, line-art vectorization, layers/text/dimensions, export and drawing review | [SKILL.md](subskills/autocad-automation/SKILL.md) |

## Routing examples / Yönlendirme örnekleri

| User request / Kullanıcı isteği | Route |
|---|---|
| “Parameterize this brief”; “Önce parametrik tasarım planı hazırla” | VibeCAD |
| “CNC mounting base”; “Radyüs ve pah içeren CNC montaj tabanı” | CNC fillet/chamfer |
| “M6 tapped hole”; “M6 kılavuz deliği oluştur” | Threaded holes |
| “Create or edit DWG/DXF”; “AutoCAD ile teknik çizim hazırla” | AutoCAD |
| “Generate part/assembly drawing”; “Ölçü zinciri, delik tablosu ve BOM içeren teknik resim hazırla” | Engineering drawing |

```text
Natural-language requirements
  → structured design_plan.json
  → specialist subskill by part/task type
  → engineering-drawing subskill when needed
  → parent scripts/sw_*.py native execution
  → sw_review.run_review()
```

The drawing subskill may be called by the root skill, VibeCAD, CNC/hole workflows or the orchestrator; other subskills do not need a reverse dependency.

For final line-art-to-CAD results, preserve only source-derived vectorized lines. Do not retain guessed outer contours, facial ellipses, logo triangles, water lines, replacement text or in-drawing review notes.

## Subskill structure

```text
subskills/<name>/
├── SKILL.md       # Agent entry point and workflow
├── README.md      # Human entry point
├── manifest.yaml  # Index metadata
├── scripts/       # Reusable scripts
├── references/    # Tested lessons and API details
├── examples/      # Sample inputs/outputs
└── agents/        # Optional client metadata
```

Each subskill must state applicable and excluded tasks, parent wrappers to use, API stability/fallback strategies, required outputs and review gates. Record newly discovered failure modes in its references. Apply the [language policy](localization/README.md) to new content.
