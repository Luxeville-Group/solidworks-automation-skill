# CAD Programming-Language Backend Routing

## Core principles

Do not generalize an individual `I*` method being unavailable from Python into the entire capability being unavailable.
First distinguish a business capability from an exact interface, then choose in this order:

1. Prefer Python `pywin32` when a non-`I` counterpart, `CreateMassProperty` or another Automation-compatible interface exists.
2. For `SAFEARRAY`, `BYREF` or `object/out` marshaling differences, try explicit `VARIANT`, then `comtypes`, then C# PIA, and read back real artifacts.
3. Use an isolated native C++ add-in/bridge only when official documentation requires in-process unmanaged C++ and the task needs those raw-interface semantics.
4. Prefer C# add-ins for events, PropertyManagerPage, TaskPane and long-lived callbacks.
5. Changing languages cannot overcome missing licenses/add-ins or data the API does not expose.

## Executable queries

```powershell
# List all atomic operations and candidate backends.
python scripts/backend_router.py --list

# Ordinary low-level array task: allow Automation equivalents and prefer Python.
python scripts/backend_router.py `
  --operation solidworks_pointer_array_api `
  --available solidworks-com-pywin32

# Explicit raw I* pointer semantics: select native C++.
python scripts/backend_router.py `
  --operation solidworks_pointer_array_api `
  --available solidworks-com-pywin32 `
  --available solidworks-native-cpp `
  --exact-api

# Known SW2026 SP1.1 hold-line blocker: returns KNOWN_HOST_REVISION_BLOCKER.
python scripts/backend_router.py `
  --operation fillet_hold_lines_exact `
  --available solidworks-native-cpp `
  --solidworks-revision 34.1.1
```

`capabilities.yaml` is the single source of truth for capabilities and routing. Pass the actually detected backends,
SolidWorks revision, add-ins and license conditions to the router; a registry entry does not mean local availability.
Without `--available`, the router conservatively returns `unavailable` instead of assuming runtimes are installed.

## Verified interface boundaries

| Interface/scenario | Official boundary | Preferred strategy |
|---|---|---|
| `ISldWorks.IGetDocuments` | Pointer array; in-process unmanaged C++ only | Automation for ordinary traversal; C++ for exact raw semantics |
| `IModelDocExtension.IGetMassProperties` / `IBody2.IGetMassProperties` | Double-pointer array; unsupported by managed languages | Prefer `GetMassProperties` / `CreateMassProperty`; C++ only for raw arrays |
| `IModelDocExtension.IListExternalFileReferences` | Multiple pointer arrays; in-process unmanaged C++ only | Supported dependency/reference Automation APIs first; C++ for strict raw semantics |
| `ISldWorks.IGetDocumentDependencies2` | Native string pointers; in-process unmanaged C++ only | `GetDependencies2` for normal delivery; C++ for the raw interface |
| `IModelDoc2.IGetConfigurationNames` | Name-pointer array; in-process unmanaged C++ only | Python/C# use `GetConfigurationNames` |
| `ISimpleFilletFeatureData2.ISetHoldLines` | In-process unmanaged C++ only | Native C++ is the only exact path; known SW2026 SP1.1 host failure remains blocked |
| `IPropertyManagerPage2` / events / TaskPane | Stable handlers and add-in lifecycle required | C# add-in; Python for external orchestration only |
| Exact `IAnnotation` text bounds | Required data not exposed | Conservative estimates + PDF/image readback + visual review; another language cannot fabricate the data |

Official references:

- [IGetDocuments](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~IGetDocuments.html)
- [IGetMassProperties](https://help.solidworks.com/2026/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDocExtension~IGetMassProperties.html)
- [IListExternalFileReferences](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~IListExternalFileReferences.html)
- [IGetDocumentDependencies2](https://help.solidworks.com/2026/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~IGetDocumentDependencies2.html)
- [IGetConfigurationNames](https://help.solidworks.com/2026/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDoc2~IGetConfigurationNames.html)
- [ISetHoldLines](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISimpleFilletFeatureData2~ISetHoldLines.html)
- [C# add-in template and event structure](https://help.solidworks.com/2026/English/api/sldworksapiprogguide/Overview/Using_SolidWorks_C__Add-In_Wizard_to_Create_C__Add-In.htm)
- [PropertyManagerPage2](https://help.solidworks.com/2026/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IPropertyManagerPage2.html)

## Current capability classification

- Python remains the default orchestration language for normal modeling, assemblies, drawings, export, configuration families, properties and auditing.
- C# PIA is a strongly typed Automation marshaling fallback, not a substitute for unmanaged `I*` pointer interfaces.
- C# add-ins handle events, UI and long-lived host lifecycles.
- Native C++ handles officially restricted interfaces and necessary high-throughput geometry; require version allowlists, crash isolation and real-machine regressions.
- SWBasic/VBA supports minimal main-thread reproductions and compatibility diagnosis; it does not replace native C++.
- Python/OCP handles headless open-format geometry; it cannot create native SolidWorks feature trees.
- Prefer C# .NET for native AutoCAD DWG database operations rather than forcing unstable ActiveX through Python.
- Python generates CalculiX/Elmer inputs, orchestrates native solvers and audits results; a passing run is not engineering certification.

## Remaining extensions

In descending priority:

1. Productionize the C# add-in: main-thread queue, versioned installer, Authenticode and upgrade/rollback. Basic events, PropertyManagerPage and TaskPane passed real SW2026 tests.
2. Safe native C++ bridge: wrap only officially verified unmanaged interfaces, with per-entry process/version gates.
3. Sheet metal: multiple bends, sequence, forming tools and complex flat-pattern interference. U-profile flanges and flat DXF passed real tests.
4. Weldments: gussets, end caps, complex corners and multiconfiguration cut lists. HSS rectangular frames and length/angle readback passed real tests.
5. Configuration families: derived configurations, display states, configuration-specific suppression and design tables; do not reuse unverified legacy signatures.
6. Native Routing/Simulation adapters: enable only with complete add-in and licensing evidence.
