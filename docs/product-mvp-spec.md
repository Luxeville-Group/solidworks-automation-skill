# CAD Automation Delivery Workbench MVP Specification

Version: v0.1
Date: 2026-07-25
Related research: `docs/market-research-2026.md`

## 1. Product positioning

Working product name:

```text
CAD Automation Delivery Workbench
```

One sentence:

```text
A local software workflow for mechanical engineers and 3D-printing prototype users, taking common structural parts from parameter input through modeling, drawings, standards review, and delivery archiving.
```

The first version does not build new CAD, cloud collaboration, or complete PLM. It completes one real workflow:

```text
Automated delivery of a 3D-printed enclosure
```

## 2. MVP success criteria

On a local Windows computer, users can:

1. Create a 3D-printed enclosure project.
2. Enter overall dimensions, wall thickness, holes, slots, screw bosses, and interfaces.
3. Invoke SolidWorks to generate a 3D model with actual cuts.
4. Invoke SolidWorks Drawing or AutoCAD to generate engineering drawings.
5. Automatically check drawings against P0 rules.
6. Produce a complete delivery package.

### Acceptance metrics

| Metric | MVP target |
|---|---|
| Project creation to parameter confirmation | Within five minutes |
| Modeling script execution | Within 10 minutes |
| Initial engineering drawing | Within five minutes |
| Missing P0 drawing annotations | Must be zero |
| Output traceability | Every file recorded in the manifest |
| Diagnosable failures | Every failure identifies stage, cause, and recommendation |

## 3. Technical boundaries

### Local execution required

No rented server or cloud task queue. All CAD files, reference images, parameters, and review reports remain on the user's computer.

Recommended stack:

```text
Desktop UI: PySide6 / Qt
Automation scripts: Python + pywin32/comtypes
CAD control: SolidWorks COM + AutoCAD COM
Project data: local JSON / Markdown / folders
Packaging: PyInstaller
Updates: GitHub repository
```

### Excluded features

- No CAD geometry kernel.
- No browser web service.
- No collaboration.
- No account system.
- No promise of fully automatic arbitrary complex parts.
- No enterprise PDM/PLM integration.
- No arbitrary Python/VBA/AutoLISP execution interface for ordinary users.

## 4. Initial user profile

### Primary users

Independent mechanical designers, automation-equipment engineers, makers, and 3D-printing prototype users.

Their main concerns:

- Whether holes are genuinely cut.
- Whether the output can be 3D-printed directly.
- Whether drawings follow Chinese engineers' conventions (the original target market).
- Whether hole, slot, and interface annotations are complete.
- Whether files can be sent directly to machining/printing providers or customers.

### Prerequisites

The user's computer requires:

- Windows.
- SolidWorks installed and launched at least once.
- AutoCAD installed and launched at least once; optional initially if using SolidWorks Drawing only.
- Python 3.10+.
- `pywin32` / `comtypes`.

## 5. Information architecture

The first desktop version uses left navigation, a central task form, and a right review/output panel.

```text
┌────────────────────────────────────────────────────────────────┐
│ CAD Automation Delivery Workbench                               │
├──────────────┬──────────────────────────┬──────────────────────┤
│ Projects      │ Task: 3D-printed enclosure │ Review status       │
│ New project   │                            │ P0 standards checks │
│ Templates     │ Dimensions / Holes / Bosses│ Output files        │
│ Build model   │ Drawings / Requirements    │ Execution log       │
│ Build drawing │                            │                     │
│ Review        │ [Save parameters] [Model]  │ [Open output folder]│
│ Delivery      │ [Drawings] [Review all]    │                     │
│ Skills        │                            │                     │
└──────────────┴──────────────────────────┴──────────────────────┘
```

## 6. Core workflow

### 6.1 Create a project

User inputs:

- Project name.
- Project type: `3d_print_shell`.
- Output directory.
- Units: default `mm`.
- Drawing style: default `GB/T style`.
- Require AutoCAD DWG/DXF: enabled by default.
- Require native SolidWorks drawings: optional.

System actions:

1. Create the project directory.
2. Write `project.json`.
3. Create `inputs/`, `outputs/`, `reviews/`, `previews/`, and `logs/`.
4. Check SolidWorks/AutoCAD/Python dependencies.

### 6.2 Upload reference images

Supported formats:

- `jpg`
- `png`
- `jpeg`
- `bmp`

Uses:

- Appearance reference.
- Assistance with hole and interface placement.
- Not a direct basis for manufacturing dimensions.

Rule:

Reference images cannot replace dimensions. Every hole, slot, interface opening, fluid port, screw hole, and screw boss must have specifications and locations in the parameter table.

### 6.3 Enter parameters

Use a structured form; prompts supply supplementary notes only.

Required sections:

- Overall dimensions.
- Wall/bottom thickness.
- Fillets/chamfers.
- Holes/slots.
- Screw bosses/mounting holes.
- Drawing settings.
- Technical requirements.

### 6.4 Generate the model

System actions:

1. Read `parameters.json`.
2. Generate or invoke a SolidWorks modeling script.
3. Create the enclosure body.
4. Shell the body or perform Boolean cuts.
5. Make real cuts for every hole, slot, and interface.
6. Add screw bosses, ribs, fillets/chamfers.
7. Save `SLDPRT`.
8. Export `STEP` and `STL`.
9. Review the model.

Required checks:

- Model is nonempty.
- Overall dimensions match parameters.
- Wall thickness exists.
- Hole/slot counts match the parameter table.
- Holes/slots are actual cuts, not decorative sketch lines.
- STL exists and has a reasonable size.

### 6.5 Generate engineering drawings

Support two routes:

| Route | Use case |
|---|---|
| SolidWorks Drawing | Generate three orthographic views/isometric views, dimensions, and PDF from the model |
| AutoCAD DWG/DXF | Generate DWG/DXF drawings customary in China, hole/slot tables, and title blocks |

The MVP prioritizes AutoCAD DWG/DXF because the original user explicitly requested formats common in China and strict annotation rules.

Drawings must contain:

- Drawing frame.
- Title block.
- Units.
- Scale.
- Front view.
- Top view.
- Right view or necessary section view.
- Isometric reference view.
- Overall dimensions.
- Wall/bottom thickness.
- Hole/slot specifications and quantities.
- Hole/slot locating dimensions.
- Technical requirements.
- Hole/slot schedule.

### 6.6 Standards review

Review comprises machine checks and visual inspection.

Machine checks:

- File existence.
- Reasonable DWG/DXF bounding boxes.
- Required layers present.
- Sufficient dimension entities.
- Hole/slot entity counts match parameters.
- Title block present.
- Hole/slot schedule present.
- Complete review.json schema.

Visual inspection:

- Dimension lines do not overlap geometry.
- Leaders do not cross views.
- Text does not overlap.
- Annotations do not intrude into the title block.
- Hole/slot locations are understandable.
- Drawing presentation is acceptable to Chinese mechanical engineers.

## 7. Page specifications

### 7.1 Home / project list

Display:

- Recent projects.
- Project name.
- Type.
- Last modification time.
- Latest status.
- Output directory.

Actions:

- Create project.
- Open project.
- Open output directory.
- Duplicate project.
- Delete the project record without deleting source files unless the user explicitly chooses file deletion.

### 7.2 New project page

Fields:

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| project_name | text | Empty | Yes | Project name |
| project_type | select | 3D-printed enclosure | Yes | Only one type in the MVP |
| output_root | folder | User selection | Yes | Output root directory |
| unit | select | mm | Yes | Only mm initially supported |
| drawing_standard | select | GB/T style | Yes | Expandable to company templates later |
| need_dwg | checkbox | true | No | Output DWG |
| need_dxf | checkbox | true | No | Output DXF |
| need_pdf | checkbox | true | No | Output PDF |
| need_stl | checkbox | true | No | Output STL |
| need_step | checkbox | true | No | Output STEP |

### 7.3 Parameter page

#### Overall geometry

| Field | Type | Units | Required | Validation |
|---|---|---|---|---|
| outer_length | number | mm | Yes | > 0 |
| outer_width | number | mm | Yes | > 0 |
| outer_height | number | mm | Yes | > 0 |
| wall_thickness | number | mm | Yes | >= 0.8 |
| bottom_thickness | number | mm | Yes | >= 0.8 |
| corner_radius | number | mm | No | >= 0 |
| edge_chamfer | number | mm | No | >= 0 |
| shell_open_direction | select | - | Yes | top / bottom / side |

#### 3D printing parameters

| Field | Type | Units | Default | Description |
|---|---|---|---|---|
| print_process | select | - | FDM | FDM / SLA / SLS; MVP prioritizes FDM |
| nozzle_diameter | number | mm | 0.4 | FDM nozzle |
| hole_compensation | number | mm | 0.2 | Suggested diameter oversizing |
| fit_clearance | number | mm | 0.3 | Assembly clearance |
| min_wall_warning | number | mm | 1.2 | Warn below this value |

#### Hole parameters

Every hole requires:

- Type.
- Specification.
- Quantity.
- Face.
- Datum edge.
- Center location.

Fields:

| Field | Type | Units | Required | Description |
|---|---|---|---|---|
| id | text | - | Yes | For example H1 |
| name | text | - | Yes | For example Display mounting hole |
| hole_type | select | - | Yes | round / counterbore / countersink / threaded / slot |
| face | select | - | Yes | front / back / left / right / top / bottom |
| diameter | number | mm | Conditional | Circular hole diameter |
| width | number | mm | Conditional | Slot width |
| length | number | mm | Conditional | Slot length |
| quantity | number | count | Yes | >= 1 |
| datum_x | select | - | Yes | left / right / centerline |
| datum_y | select | - | Yes | bottom / top / centerline |
| center_x | number | mm | Yes | Relative to X datum |
| center_y | number | mm | Yes | Relative to Y datum |
| pitch_x | number | mm | Conditional | Horizontal hole spacing |
| pitch_y | number | mm | Conditional | Vertical hole spacing |
| through | checkbox | - | Yes | Whether a through hole |
| note | text | - | No | Process notes |

#### Interface openings

Interface openings are subject to mandatory hole/slot rules; prose alone is insufficient.

Common types:

- USB-C.
- Circular DC connector hole.
- HDMI.
- RJ45.
- Button opening.
- Indicator-light hole.
- Display window.
- Fluid port.
- Ventilation slot.

Interface fields:

| Field | Type | Units | Required |
|---|---|---|---|
| id | text | - | Yes |
| interface_type | select | - | Yes |
| face | select | - | Yes |
| cutout_width | number | mm | Conditional |
| cutout_height | number | mm | Conditional |
| cutout_diameter | number | mm | Conditional |
| corner_radius | number | mm | No |
| center_x | number | mm | Yes |
| center_y | number | mm | Yes |
| quantity | number | count | Yes |
| clearance | number | mm | No |

#### Screw-boss parameters

| Field | Type | Units | Required | Description |
|---|---|---|---|---|
| id | text | - | Yes | For example B1 |
| screw_size | select | - | Yes | M2 / M2.5 / M3 / M4 |
| boss_outer_diameter | number | mm | Yes | Screw-boss outside diameter |
| hole_diameter | number | mm | Yes | Screw hole or insert hole |
| boss_height | number | mm | Yes | Screw-boss height |
| face | select | - | Yes | Face containing the feature |
| center_x | number | mm | Yes | X location |
| center_y | number | mm | Yes | Y location |
| quantity | number | count | Yes | Quantity |
| rib_enabled | checkbox | - | No | Whether to add reinforcing ribs |

### 7.4 Execution page

Display stages:

```text
preflight -> build_model -> export_model -> build_drawing -> export_drawing -> review -> package
```

Each stage displays:

- Status: waiting / running / passed / warning / failed.
- Start time.
- End time.
- Log summary.
- Failure cause.
- Recommended action.

### 7.5 Review report page

Four sections:

1. Model review.
2. Drawing review.
3. 3D printing review.
4. Delivery package review.

Statuses:

- `pass`: deliverable.
- `warning`: deliverable subject to human confirmation.
- `fail`: not deliverable; rework required.

Any failed P0 rule makes the overall status `fail`.

## 8. Project directory structure

Store every project in its own folder:

```text
<output_root>/<project_slug>/
├── project.json
├── parameters.json
├── inputs/
│   ├── reference_001.png
│   └── brief.md
├── generated/
│   ├── build_model.py
│   ├── build_drawing.py
│   └── drawing_plan.json
├── outputs/
│   ├── model/
│   │   ├── <project>.sldprt
│   │   ├── <project>.step
│   │   └── <project>.stl
│   ├── drawing/
│   │   ├── <project>.dwg
│   │   ├── <project>.dxf
│   │   └── <project>.pdf
│   └── package/
│       └── <project>_delivery.zip
├── previews/
│   ├── model_iso.png
│   ├── model_front.png
│   ├── drawing_preview.png
│   └── package_cover.png
├── reviews/
│   ├── model_review.json
│   ├── drawing_review.json
│   ├── printability_review.json
│   └── final_review.json
├── logs/
│   └── run_YYYYMMDD_HHMMSS.log
└── README_delivery.md
```

## 9. Data file specifications

### 9.1 project.json

```json
{
  "schema_version": "0.1",
  "project_id": "20260725_001",
  "project_name": "ai_cpu_cooling_shell",
  "project_type": "3d_print_shell",
  "unit": "mm",
  "drawing_standard": "GB_T_style",
  "created_at": "2026-07-25T20:00:00+08:00",
  "updated_at": "2026-07-25T20:00:00+08:00",
  "output_root": "C:/Users/current/Documents/CADAutomationWorkbench",
  "status": "draft"
}
```

### 9.2 parameters.json

```json
{
  "schema_version": "0.1",
  "units": "mm",
  "shell": {
    "outer_length": 120,
    "outer_width": 80,
    "outer_height": 35,
    "wall_thickness": 1.6,
    "bottom_thickness": 2.0,
    "corner_radius": 4,
    "edge_chamfer": 0.5,
    "open_direction": "top"
  },
  "printing": {
    "process": "FDM",
    "nozzle_diameter": 0.4,
    "hole_compensation": 0.2,
    "fit_clearance": 0.3,
    "min_wall_warning": 1.2
  },
  "features": {
    "holes": [],
    "cutouts": [],
    "bosses": [],
    "vents": []
  },
  "drawing": {
    "paper_size": "A3",
    "scale": "1:1",
    "title": "3D-printed enclosure",
    "material": "PLA/PETG",
    "projection": "first_angle",
    "required_exports": ["dwg", "dxf", "pdf", "png"]
  }
}
```

### 9.3 final_review.json

```json
{
  "schema_version": "0.1",
  "overall_status": "fail",
  "project_id": "20260725_001",
  "checked_at": "2026-07-25T20:30:00+08:00",
  "checks": [
    {
      "id": "drawing-hole-position-complete",
      "severity": "P0",
      "status": "fail",
      "target": "drawing",
      "message": "Interface opening I1 lacks X/Y center locating dimensions",
      "suggestion": "Add center locating dimensions relative to the left and bottom edges"
    }
  ],
  "outputs": {
    "sldprt": "outputs/model/project.sldprt",
    "step": "outputs/model/project.step",
    "stl": "outputs/model/project.stl",
    "dwg": "outputs/drawing/project.dwg",
    "dxf": "outputs/drawing/project.dxf",
    "pdf": "outputs/drawing/project.pdf",
    "preview": "previews/drawing_preview.png"
  }
}
```

## 10. P0 standards checklist

### 10.1 Model P0

| ID | Check | Failure condition |
|---|---|---|
| model-file-exists | Model files exist | SLDPRT/STEP/STL missing or abnormally sized |
| model-solid-body | Main body exists | No solid body or unexpected body count |
| model-shell-thickness | Wall/bottom thickness exists | Thickness not modeled or below user parameters |
| model-cut-through | Actual hole cuts | Holes/slots are only sketches/lines/decorations and do not cut through specified faces |
| model-feature-count | Matching feature count | Hole/slot count differs from parameter table |
| model-print-scale | Correct dimensions/units | STL scale does not correspond to millimeters |

### 10.2 Drawing P0

| ID | Check | Failure condition |
|---|---|---|
| drawing-frame-title | Frame and title block | Missing frame, title block, units, or scale |
| drawing-main-dimensions | Overall dimensions | Missing length, width, or height |
| drawing-wall-dimensions | Wall/bottom thickness | 3D-printed enclosure lacks wall or bottom thickness dimensions |
| drawing-hole-spec | Hole/slot specifications | Missing specifications, quantities, or types |
| drawing-hole-position | Hole/slot location | Missing X/Y locations, center distances, or datum dimensions |
| drawing-real-dimensions | Real dimension entities | Critical dimensions faked with drawn lines or plain text |
| drawing-leader-crossing | Crossing leaders | Long leaders cross views, holes, centerlines, or text |
| drawing-overlap | Drawing overlap | Overlapping dimensions/text/tables impede reading |
| drawing-title-intrusion | Title-block intrusion | Dimension lines or text enter the title block |
| drawing-hole-table | Hole/slot schedule | Dense features lack a table, or table lacks specifications/quantities/locations |

### 10.3 3D printing P0

| ID | Check | Failure condition |
|---|---|---|
| print-min-wall | Minimum wall thickness | Below the user's hard minimum |
| print-open-hole | Required openings | User requests holes but model lacks cuts |
| print-fit-clearance | Assembly clearance | Parameters require assembly but no clearance exists |
| print-stl-valid | STL export | Missing/empty file or incorrect scale |

## 11. Default drawing style

The MVP defaults to Chinese mechanical drawing conventions from the original specification.

Defaults:

| Item | Default |
|---|---|
| Sheet | A3, or A4 when needed |
| Units | mm |
| Scale | 1:1; 1:2 / 2:1 when needed for fit |
| Font | Original specification: FangSong-style Chinese font, falling back to an available Chinese font with the substitution recorded; localized outputs must use appropriate Turkish/English fonts |
| Lines | Separate layers for thick continuous, thin continuous, center, hidden, and dimension lines |
| Title block | Lower right |
| Views | Front, top, right/section, isometric reference |
| Tables | Prefer hole/slot schedules |

Note:

```text
Following GB/T style does not replace company drawing review. A user-provided company template takes priority.
```

## 12. Delivery package specification

The delivery package must contain:

```text
01_model/
  project.sldprt
  project.step
  project.stl

02_drawing/
  project.dwg
  project.dxf
  project.pdf
  drawing_preview.png

03_review/
  model_review.json
  drawing_review.json
  printability_review.json
  final_review.json

04_source/
  project.json
  parameters.json
  generated_scripts/

README_delivery.md
```

`README_delivery.md` must state:

- Project name.
- Units.
- Material/printing-process assumptions.
- Output file descriptions.
- Drawing-standard explanation.
- Review status.
- Items still requiring human confirmation.

## 13. State machine

Project states:

```text
draft -> ready -> running -> generated -> reviewing -> pass
                                      -> warning
                                      -> failed
```

Stage states:

```text
waiting
running
passed
warning
failed
skipped
```

Rules:

- Any P0 failure makes project status `failed`.
- A P1 failure may produce project status `warning`.
- Project status may be `pass` only when all required outputs exist and P0 checks pass.

## 14. Error handling

Errors must be recorded structurally.

```json
{
  "stage": "build_drawing",
  "error_code": "AUTOCAD_COM_REJECTED",
  "message": "AutoCAD COM call rejected",
  "retryable": true,
  "suggestion": "Retry when AutoCAD is idle; close dialogs or restart AutoCAD if necessary"
}
```

Common errors:

| Error code | Stage | Handling |
|---|---|---|
| SOLIDWORKS_NOT_FOUND | preflight | Prompt to install or start SolidWorks |
| PYWIN32_MISSING | preflight | Prompt to install dependencies |
| AUTOCAD_NOT_FOUND | preflight | Prompt to install or start AutoCAD |
| AUTOCAD_COM_REJECTED | build_drawing | Retry serially; prompt user to close dialogs if needed |
| FEATURE_PARAM_INCOMPLETE | validate_parameters | Block generation and request missing hole/slot locations |
| MODEL_CUT_MISSING | review_model | Rework the model |
| DRAWING_DIM_MISSING | review_drawing | Rework the drawing |
| EXPORT_FILE_MISSING | package | Export again |

## 15. MVP interface priorities

### P0 pages

- Home/project list.
- New project.
- 3D-printed enclosure parameters.
- Execution log.
- Review report.
- Output files.

### P1 pages

- Skill version management.
- Rule-library configuration.
- Company template import.
- Duplicate historical projects.

### P2 pages

- Visual hole-location editor.
- 3D preview.
- Online drawing annotations.
- Multitemplate marketplace.

## 16. Development breakdown

### First runnable version

Goal:

```text
Create projects, save parameters, run one mock execution, and generate review.json and a delivery directory.
```

Tasks:

1. Create the desktop project directory.
2. Implement the main window and navigation.
3. Implement project creation.
4. Implement the parameter form.
5. Implement local JSON persistence.
6. Implement the mock execution state machine.
7. Implement opening the output directory.

### Second version

Goal:

```text
Integrate SolidWorks and generate a real 3D-printable enclosure model.
```

Tasks:

1. Integrate `sw_preflight.py`.
2. Integrate SolidWorks modeling scripts.
3. Export SLDPRT/STEP/STL.
4. Generate model previews.
5. Generate model review reports.

### Third version

Goal:

```text
Integrate AutoCAD to generate DWG/DXF drawings meeting P0 rules.
```

Tasks:

1. Integrate `acad_preflight.py`.
2. Generate drawing_plan.json.
3. Invoke AutoCAD drawing creation.
4. Export DWG/DXF/PDF/PNG.
5. Implement P0 drawing review.

### Fourth version

Goal:

```text
One-click delivery package.
```

Tasks:

1. Collect all outputs.
2. Write delivery instructions.
3. Compress the delivery package.
4. Build a final status page.

## 17. Open questions for the first version

Further validation required:

- AutoCAD preview-export stability across versions.
- Whether SolidWorks Drawing or AutoCAD Drawing reduces rework more.
- Reliable detection that holes/slots cut through real geometry.
- Which P0 drawing checks can be automated and which need human visual confirmation.
- Whether to use built-in drawing-frame templates or require company template import.

## 18. Next step

Proceed to prototype design:

```text
apps/desktop/
```

Minimum implementation:

- PySide6 main window.
- Project creation.
- Parameter form.
- Local project directory generation.
- Mock execution and review.json.

Integrate SolidWorks and AutoCAD after the mock prototype works. This validates the user workflow before COM stability becomes a constraint.
