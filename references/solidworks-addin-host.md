# SolidWorks C# Add-in Host

## Purpose

`dotnet/CadStudio.SolidWorks.AddinHost` is a `net48/x64` in-process host for
long-lived event callbacks and native UI lifecycles. It does not replace short-lived Python modeling scripts or emulate
unmanaged-C++-only `I*` pointer interfaces; `capabilities.yaml::solidworks_addin_ui_events` selects this route.

The host includes:

- `ISwAddin.ConnectToSW/DisconnectFromSW` and `SetAddinCallbackInfo2`;
- `SldWorks` coclass active-document, new/open and special-close events;
- A three-command `CommandGroup`;
- A WinForms `TaskPane` with 64-bit window handles;
- All 37 callbacks of SW2026 `IPropertyManagerPage2Handler9`;
- Diagnostic evidence at `%LOCALAPPDATA%\CAD Studio\SolidWorksAddin\host-status.json`;
- Strong-name assembly identity, CurrentUser COM smoke testing and Machine registration deployment paths.

## Build

Explicitly provide the local PIA directory to avoid referencing the wrong SolidWorks major version:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sw_addin_host.ps1 `
  -Action Build `
  -SolidWorksApiDir 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
```

Build output is an assembly; Machine registration also generates and registers a TLB in the same directory:

```text
dotnet\CadStudio.SolidWorks.AddinHost\bin\Release\net48\CadStudio.SolidWorks.AddinHost.dll
dotnet\CadStudio.SolidWorks.AddinHost\bin\Release\net48\CadStudio.SolidWorks.AddinHost.tlb
```

## Registration and verification

CurrentUser mode verifies only CLR/COM activation; it does not create misleading SolidWorks Add-ins discovery entries:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sw_addin_host.ps1 -Action Register -RegistrationScope CurrentUser -SolidWorksApiDir '<api\redist>'
powershell -ExecutionPolicy Bypass -File scripts\sw_addin_host.ps1 -Action ComSmoke -RegistrationScope CurrentUser
```

In-process SolidWorks loading requires Machine registration. A normal PowerShell session prompts once for UAC;
the elevated subprocess performs only the fixed-GUID build/registration actions:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sw_addin_host.ps1 -Action Register -RegistrationScope Machine -SolidWorksApiDir '<api\redist>'
powershell -ExecutionPolicy Bypass -File scripts\sw_addin_host.ps1 -Action Probe -RegistrationScope Machine
```

Machine mode uses 64-bit `.NET Framework RegAsm /codebase /tlb` and registers COM classes, the type library,
`HKLM\SOFTWARE\SOLIDWORKS\Addins\{GUID}` and the current-user startup entry. Uninstall with the same assembly path:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sw_addin_host.ps1 -Action Unregister -RegistrationScope Machine
```

## Acceptance gates

`ISldWorks.LoadAddIn()` returning `swSuccess=0` alone is insufficient. A real probe must read diagnostics and verify:

1. `status == connected`;
2. `callbackRegistered == true`;
3. CommandGroup, TaskPane and PropertyManagerPage are all `true`;
4. Creating a temporary part increments `file_new` and active-document event counts, and after `CloseDoc`, `GetDocumentCount()==0`;
5. `errors` is empty.

Use `python scripts/sw_addin_host.py` or MCP `solidworks_addin_host_status` to inspect the assembly, TLB, registration level,
diagnostics and precise blocking codes. Current-user COM registration cannot replace these Machine gates.

## Real SW2026 evidence

The complete local SW2026 SP1.1 (Revision `34.1.1`) regression passed:

- The add-in was instantiated by `SLDWORKS.exe`, with `LoadAddIn=0`;
- `SetAddinCallbackInfo2`, application events, three-command CommandGroup, TaskPane and PropertyManagerPage were ready;
- All 37 `IPropertyManagerPage2Handler9` callbacks used a public, COM-visible handler exposing `AutoDispatch`;
- New-document event count was 1, open-document count returned to 0 after closing the temporary part, and diagnostics contained no errors;
- Results were written to `output/addin-host-real/addin_host_regression_result.json`.

The regression also confirmed two gates: without a TLB, SW2026 may load the DLL and return `LoadAddIn=0` without instantiating
`ISwAddin`; when the PMP handler exposes only `IUnknown` without `IDispatch`, `ICreatePropertyManagerPage`
throws `InvalidCastException`.

## Known limitations

- Strong-name signing provides a stable assembly identity; it is not trusted-publisher Authenticode
  code signing. Enterprise distribution should sign DLLs/installers in its release pipeline.
- SolidWorks locks loaded DLLs. Before rebuilding, use `UnloadAddIn` or exit normally; do not force overwrite.
- Application-level `FileCloseNotify` fires only after drawing `CloseAndReopen`; for ordinary parts/assemblies, inspect document count or subscribe to document events.
- CommandManager layout persists in user settings. Keep the GUID, command-group ID and user command IDs stable after release.
- Add-ins suit UI, events and persistent callbacks; use existing Python Automation wrappers for ordinary modeling.

## Official references

- [ISwAddin Members (SOLIDWORKS API Help 2026)](https://help.solidworks.com/2026/english/api/swpublishedapi/SolidWorks.Interop.swpublished~SolidWorks.Interop.swpublished.ISwAddin_members.html)
- [Using the C# Add-in Wizard (SOLIDWORKS API Help 2026)](https://help.solidworks.com/2026/English/api/sldworksapiprogguide/Overview/Using_SolidWorks_C__Add-In_Wizard_to_Create_C__Add-In.htm)
- [IPropertyManagerPage2Handler9 Members (SOLIDWORKS API Help 2026)](https://help.solidworks.com/2026/English/api/swpublishedapi/SolidWorks.Interop.swpublished~SolidWorks.Interop.swpublished.IPropertyManagerPage2Handler9_members.html)
- [LoadAddIn Method (SOLIDWORKS API Help 2026)](https://help.solidworks.com/2026/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~LoadAddIn.html)
- [FileCloseNotify Delegate (SOLIDWORKS API Help 2026)](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.DSldWorksEvents_FileCloseNotifyEventHandler.html)
