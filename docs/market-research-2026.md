# SolidWorks Automation Skill Market Research and Product Positioning

Research date: 2026-07-25

## 1. Main conclusion

Do not build a new CAD application or begin with an attractive visualization shell without functional substance.

The more valuable direction is:

```text
A local CAD automation delivery assistant for mechanical engineers and prototyping teams
```

Core value:

```text
Upload reference images/enter parameters -> Automatically model -> Generate engineering drawings -> Review against national standards and manufacturing rules -> Produce a deliverable file package
```

This avoids competing directly with SolidWorks, Inventor, Fusion, NX, and Creo, focusing on daily engineering tasks that are repetitive, error-prone, and must be done correctly.

## 2. Market signals

### 2.1 CAD and industrial R&D/design software continue growing

- Research and Markets' 2026 CAD market report segments CAD by 3D/2D, deployment, modeling approach, and industry, identifying engineering and industrial design companies among major end users.
- A 2025 Zhiyan Consulting report estimates the 2024 global industrial R&D/design software market at approximately USD 55 billion and the Chinese market at approximately CNY 35 billion, driven by smart manufacturing, digital transformation, and domestic substitution.

Assessment:

The CAD market is large, but strongly dominated by established vendors, and a complete CAD system requires enormous investment. We should build surrounding automation tools that improve productivity.

### 2.2 AI applications in mechanical engineering are becoming clear

CoLab Software's 2026 mechanical engineering AI overview groups applications into five categories:

- Engineering knowledge management
- Generative design and AI CAD modeling
- AI simulation
- Automated design review and DFM
- PLM and digital threads

The best entry points for this project are:

```text
Automated design review and DFM + engineering drawing automation + local knowledge/standards libraries
```

These tasks have clear inputs, rules, and deliverables, making them suitable for automation and straightforward to verify.

### 2.3 Major vendors are building AI, with room for specialized products

SOLIDWORKS officially positions AI CAD automation, Virtual Companions, and AURA/LEO within design workflows, emphasizing higher-value engineering work and reduced repetition.

Autodesk Fusion emphasizes design, simulation, generative design, mesh editing, plastic-part rules, and lifecycle management alongside CAD.

AutoCAD Mechanical 2026 emphasizes mechanical engineering task automation, BOM, parts lists, balloons, automatic dimensions, GD&T symbols, and standardized annotations.

Assessment:

Major vendors validate demand, but their products tend toward general-purpose, enterprise, subscription offerings. Our opportunities are:

- Local Windows workflows
- Workflows familiar to Chinese-speaking mechanical engineers (the original research's target market)
- Review of GB/T engineering drawings
- SolidWorks + AutoCAD integration
- 3D printing/small-batch prototype delivery
- Direct invocation by AI agents

## 3. Competitor observations

| Product/direction | Main capabilities | Lessons for us | Areas to avoid competing directly |
|---|---|---|---|
| SOLIDWORKS AI | Embedded AI, virtual assistants, design productivity | Confirms the trend toward AI assistants in CAD | Do not build a complete CAD kernel |
| Autodesk Fusion | CAD + simulation + generative design + lifecycle | Design-to-manufacturing integration is central | Do not build a full cloud CAD platform |
| AutoCAD Mechanical | Mechanical drawing automation, standardized annotations, BOM | Drawing standards and automatic annotations solve essential needs | Do not replace AutoCAD |
| Siemens Solid Edge 2D Drafting | 2D drawings, annotations, standards compatibility | 2D engineering drawings remain relevant | Do not build standalone 2D CAD |
| DraftAid | Automatic 2D manufacturing drawings from 3D models | Drawing automation addresses a major pain point | Avoid limiting support to English/non-Chinese standards in the original target market |
| CoLab AutoReview | Design review, DFM, issue tracking, knowledge capture | Review fits enterprise workflows more readily than generation | Do not start with a large collaboration platform |
| Leo AI | CAD-aware knowledge management and engineering knowledge reuse | Engineering knowledge and historical experience are valuable | Do not promise complex B-rep AI semantics |
| Zoo.dev | Text-to-CAD, modern geometry engine, API | Text-driven CAD is a trend | Do not develop a geometry kernel |

## 4. Target users

### 4.1 Primary users

Independent mechanical designers, makers, small studios, automation-equipment engineers, and 3D-printing prototype users.

Shared characteristics:

- Familiar with SolidWorks or AutoCAD
- Frequently design enclosures, brackets, mounting plates, panels, and heat-dissipation housings
- Need rapid STL/STEP/DWG/DXF/PDF output
- Want to avoid repeatedly drawing holes, chamfers, screw bosses, and engineering drawings
- Require GB/T-style drawings and manufacturable deliverables

### 4.2 Secondary users

Small and medium manufacturing businesses, custom automation teams, and educational/training organizations.

Needs:

- Consistent drawing standards
- Fewer drawing errors by new engineers
- Template libraries and checklists
- Less time from requirements to prototype

### 4.3 Users outside initial priorities

- Complete PLM workflows for large automotive/aerospace/defense enterprises
- Extremely complex surfaces and topology optimization
- Cloud collaborative CAD platforms
- Complete CAD systems replacing SolidWorks/NX/CATIA

## 5. Frequent engineering pain points

| Pain point | Manifestation | Automation opportunity |
|---|---|---|
| Repeated modeling of similar parts | Repeated dimension changes to enclosures, brackets, panels, and mounting plates | Parametric template library |
| Drawing annotation rework | Hole specifications without locating dimensions, overlapping dimension lines, leaders crossing views | GB/T drawing review engine |
| Unusable 3D prints | Thin walls, holes not cut through, uncompensated diameters, insufficient assembly clearance | 3D printing manufacturing rule library |
| Tedious export/delivery | Separate STL, STEP, DWG, DXF, PDF, and preview exports | One-click delivery package |
| Experience cannot be reused | Senior engineers' knowledge is not recorded | Rule library + project retrospectives |
| Unstable prompts | One sentence omits hole positions, tolerances, or materials | Form inputs + AI follow-up questions |
| Fragmented software chain | SolidWorks modeling, AutoCAD drawings, manual file organization | Local task orchestration |

## 6. Existing project assets

Available assets:

- SolidWorks automation scripts
- AutoCAD automation subskill
- Engineering drawing generation experience
- Lessons about holes, slots, and locating dimensions
- GitHub skill repository
- Initial MCP server
- Example and test scripts

Gaps:

- No user-facing task entry point
- No structured template library
- No formal GB/T drawing rules library
- No systematic DFM/3D printing rules library
- No stable schema for automatic drawing review reports
- No project file management or history
- No distributable Windows application shell

## 7. Product positioning

Suggested product name:

```text
CAD Automation Delivery Workbench
```

One sentence:

```text
Turn repetitive modeling, drawing, hole verification, and delivery-file organization into a reviewable one-click workflow.
```

Not intended as:

- A new CAD system
- A pure AI chatbot
- A cloud collaboration platform
- A toy that only generates attractive previews

Intended as:

- A local automation console for SolidWorks/AutoCAD
- A checker for Chinese mechanical drawing standards
- A 3D printing/prototype delivery assistant
- A mechanical structure template library
- A task orchestrator combining AI, rules, and CAD scripts

## 8. Suggested MVP features

### MVP goal

Enable one real task:

```text
Create a 3D-printable enclosure and output engineering drawings following Chinese mechanical drawing conventions, plus a delivery package.
```

### Required features

1. Project creation
   - Select project type: 3D-printed enclosure
   - Set output directory
   - Upload reference images

2. Parameter form
   - Overall length, width, and height
   - Wall thickness
   - Fillets/chamfers
   - Display openings, connector openings, screw holes, fluid ports, and ventilation slots
   - Require specifications, quantity, and locating datums for every hole/slot category

3. Model generation
   - Invoke SolidWorks scripts
   - Ensure holes/slots are real cuts
   - Export STL/STEP/SLDPRT

4. Drawing generation
   - Invoke AutoCAD or SolidWorks Drawing
   - Output DWG/DXF/PDF/PNG
   - Default A3/A4 frame, title block, scale, and millimeter units

5. Standards review
   - Sheet format and title block
   - Hole/slot specifications, quantities, and locating dimensions
   - Overlapping dimension lines, leaders, and text
   - Whether holes actually exist
   - Basic 3D printing wall-thickness/diameter/clearance rules

6. Delivery package
   - Archive outputs together
   - Generate `review.json`
   - Generate `README_delivery.md`

### Deferred features

- Cloud accounts
- Collaboration
- PLM/PDM integration
- Topology optimization
- Complex surface generation
- Automatic quoting
- Fully autonomous generation of arbitrary CAD by language models

## 9. Drawing-standards priorities

### P0 mandatory rules

- Every hole, slot, interface opening, fluid port, screw hole, and screw boss must have specifications, quantity, and locating dimensions.
- Long leaders must not replace critical dimension chains.
- Leaders must not cross views, holes, centerlines, or title blocks.
- Dimensions must not overlap lines, text, or drawing frames.
- Drawings require a frame, title block, units, scale, view names, and technical requirements.
- Holes in 3D-printed parts must be actual model cuts, not drawing-only illustrations.

### P1 recommended rules

- Prefer hole/slot tables or feature schedules in crowded areas.
- Prefer centerlines and datum dimensions for symmetric holes.
- Describe repeated holes with `n×Φd` or a hole table to avoid scattered annotations.
- Provide process-compensation suggestions for 3D-printed hole diameters.
- Recommend clearances for assembly fits.

### P2 advanced rules

- Automatically detect underdefined sketches.
- Detect thin walls, sharp corners, overhangs, and isolated small features.
- Detect non-manifold STL geometry, reversed normals, and open edges.
- Generate DFM suggestions automatically.

## 10. Initial 3D printing rule library

Prioritize FDM because it is common among individual users and small studios.

Suggested defaults:

| Item | Initial suggestion |
|---|---|
| Structural wall thickness | Prefer at least 1.6 mm |
| Minimum printable wall thickness | At least 0.8–1.0 mm, depending on nozzle |
| Screw-boss outside diameter | At least 2–2.5 times screw diameter; refine with M2/M3/M4 templates later |
| General hole compensation | FDM holes tend to undersize; offer 0.2–0.4 mm oversizing |
| Assembly clearance | Allow 0.2–0.5 mm for sliding/insertion fits |
| Horizontal circular holes | Prefer suggesting teardrop holes or supports |
| Small holes requiring high accuracy | Suggest post-drilling/reaming |

These rules must be configurable, not hardcoded. Printer, material, nozzle, and slicer settings affect final recommendations.

## 11. Suggested software format

Build local Windows software first, not a cloud service.

Recommended form:

```text
PySide6 desktop application + Python automation scripts + local project directory + GitHub skill updates
```

Reasons:

- No rented server required
- Direct SolidWorks/AutoCAD COM access
- Reuse existing Python scripts
- Easier executable packaging
- Engineering data remains local, fitting privacy requirements

For a more polished interface later, consider:

```text
Tauri/Electron + local Python backend
```

## 12. MVP validation metrics

First validate saved time and reduced rework, rather than maximizing feature count.

Suggested metrics:

| Metric | Target |
|---|---|
| Enclosure modeling to STL | Within 10 minutes |
| Initial engineering drawing | Within five minutes |
| Missing hole/slot annotations | Zero omissions under P0 rules |
| Printability issues | Check at least wall thickness, diameter, actual cuts, and clearance |
| Rework | Reduce multiple iterations to at most one |
| User input | Primarily forms, supplemented by prompts |

## 13. 90-day roadmap

### Weeks 1–2: Product foundation

- Create `apps/desktop` or a separate desktop project
- Build a PySide6 main window
- Add project creation, output directory, and log panel
- Read local skill status and version

### Weeks 3–4: Enclosure template

- Build a 3D-printing enclosure parameter form
- Connect SolidWorks modeling scripts
- Output STL/STEP/SLDPRT
- Add actual-hole checks

### Weeks 5–6: Drawings and review

- Connect AutoCAD/SolidWorks Drawing generation
- Output DWG/DXF/PDF/PNG
- Implement P0 drawing-standards checks
- Generate review.json

### Weeks 7–8: Delivery package

- Archive deliverables in one action
- Generate delivery instructions
- Add a project history list
- Visualize failure reasons

### Weeks 9–12: Template expansion

- Mounting plate template
- Bracket template
- Heat-dissipation housing template
- Screw-boss/insert templates
- Configurable 3D printing rule library

## 14. Risks

| Risk | Response |
|---|---|
| Unstable SolidWorks/AutoCAD COM | Serialize tasks; add retries and timeout recovery |
| Incomplete user dimensions | Required form fields + AI follow-up questions |
| Difficult fully automatic drawing-standard checks | Start with P0 rules; retain human review previews |
| Different company drawing conventions | Configurable rule library, GB/T-style defaults |
| Large variation in printing parameters | Default suggestions + user printer profiles |
| Expanding product scope | Prioritize frequent enclosure/bracket/mounting-part templates |

## 15. Next tasks

Create a product prototype specification before writing code.

Required output:

```text
docs/product-mvp-spec.md
```

Contents:

- Home-page information architecture
- First task wizard: 3D-printed enclosure
- Parameter field definitions
- Output file structure
- review.json schema
- P0 standards checklist
- Initial interface sketches

Completing this specification before the PySide6 prototype gives development a clearer direction.

## 16. Research sources

- Research and Markets: Computer Aided Design CAD Software Market Report 2026
  https://www.researchandmarkets.com/reports/5972859/computer-aided-design-cad-software-market-report
- Zhiyan Consulting: 2025 assessment of China's industrial R&D/design software market size, industry chain, competitive landscape, and development trends
  https://www.chyxx.com/industry/1217927.html
- SOLIDWORKS: AI Product Design with Embedded AI Tools
  https://www.solidworks.com/product/solidworks-design/ai-overview
- SOLIDWORKS: AI CAD Tools for Workflow Optimization
  https://www.solidworks.com/solution/solidworks-ai-cad-tools-workflow-optimization
- Autodesk Fusion: Design AI solutions
  https://www.autodesk.com/solutions/generative-design-ai-software
- Autodesk AutoCAD Mechanical Toolset
  https://www.autodesk.com/products/autocad/included-toolsets/autocad-mechanical
- Siemens Solid Edge 2D Drafting
  https://resources.sw.siemens.com/en-US/download-free-2d-cad-software/
- CoLab Software: Best AI Tools & Agents for Mechanical Engineers 2026
  https://www.colabsoftware.com/ai-tools-for-mechanical-engineers-guide
- CoLab Software: Design for Manufacturability Reviews
  https://www.colabsoftware.com/use-case/design-for-manufacturability
- DraftAid: AI CAD Drawing Automation
  https://draftaid.io/
- Zoo.dev: Zookeeper and Text-to-CAD
  https://zoo.dev/zookeeper
- Leo AI: Engineering-grade AI for mechanical engineers
  https://www.getleo.ai/
- National Standards Full-Text Disclosure: GB/T 4458.4-2003, Mechanical drawings — Dimensioning
  https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=08588A5F3FE19F16B9EE8D5D87E064D5
- National Standards Full-Text Disclosure: GB/T 4457.4-2002, Mechanical drawings — General principles of presentation — Lines
  https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=5B789BF5B537CF6F89B5D743DA71D883
- National Standards Full-Text Disclosure: GB/T 10609.1-2008, Technical drawings — Title blocks
  https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=0F8577CB9AB82D5819048A87920CABAB
- JLC3DP: 3D Printing Design Guideline
  https://jlc3dp.com/help/article/3d-printing-design-guideline
- Prusa Knowledge Base: Modeling with 3D printing in mind
  https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135
- Formlabs: Minimum Wall Thickness for 3D Printing
  https://formlabs.com/blog/minimum-wall-thickness-3d-printing/
