# CAD Studio desktop workbench

This is the CAD Studio React + Tauri desktop client. Its user interface is Turkish and retains English CAD and API terminology; technical documentation is English. See the [Turkish quick start](README.tr.md).

The design uses a light desktop window, an appearance center, local wallpaper import, a right-hand Inspector, visible P0 gates, and executable workflows.

Two execution modes are supported:

- Vite browser preview for fast UI development.
- Tauri desktop application for building a Windows `.exe`.

## Features

- An appearance popover in the upper right supports local images, GIFs, and video wallpapers, with brightness, blur, and vignette controls.
- Local configuration remembers the current and recent wallpapers, appearance controls, and recent imported-model paths.
- A local automation queue persists CAD creation, model import, and delivery-package tasks as JSON.
- Agent Bridge converts graphical configuration into executable tasks for Codex, Claude Code, Gemini CLI, or OpenCode.
- CC Switch reads the current user's SQLite or legacy JSON configuration to display model routing for the selected Agent. It does not read or display secrets.
- Automatic AI planning selects task type, process, material, output formats, and checks when the user has not specified them.
- Policy Gate holds risky tasks for approval.
- Artifact Ledger records output existence, file size, and SHA-256.
- The desktop queue panel starts and stops a local Python worker and shows its state and PID.
- Worker Health provides heartbeat status; Reviewer Gate reviews artifacts and format signatures.
- Tasks awaiting review can be approved or rejected manually, recording reviewer, time, conclusion, and audit events.
- The default animated cherry-blossom wallpaper has its audio track and location metadata removed. Aurora, Blueprint, Studio, and Mist backgrounds are also available, along with local image/GIF/video import.
- A local-first knowledge base searches SolidWorks, manufacturing, and drawing guidance and can include company-standard directories.
- Optional HTTPS cloud RAG runs only when explicitly enabled and approved for external network access. Tokens are read only from environment variables.
- The window bar, light Dock navigation, project workbench, and right-hand Inspector provide the desktop layout.
- Projects support search, archive/restore, copy, and deletion. Terminal task history can be cleaned in batches. These operations remove application metadata, not delivered CAD files.
- SQLite migrations preserve the old snapshot and create project, conversation, message, and task indexes. Settings show index-count consistency.
- Buttons provide hover/press feedback and a highlight sweep on the primary action.
- Layouts support desktop and mobile preview sizes.

Release installers bundle the skill, Python worker source, and mechanical knowledge documents. Users still need Python, at least one Agent CLI, and SolidWorks/AutoCAD for real CAD operations.

See the [CAD Studio user manual](../../docs/CAD_STUDIO_USER_MANUAL.md).

In browser preview mode, imported local images can only be previewed temporarily: a browser refresh loses access to the original file path. Tauri desktop mode uses a native file picker and can restore the saved local wallpaper path at the next launch.

## Install

```powershell
cd apps\workbench-ui
npm install
```

## Development preview

```powershell
npm run dev
```

## Desktop development

```powershell
npm run desktop:dev
```

## Build the frontend

```powershell
npm run build
```

## Build the desktop application

```powershell
npm run desktop:build
```

This creates a runnable `.exe` without an installer. To build an installer:

```powershell
npm run desktop:bundle
```

Executable path:

```text
apps\workbench-ui\src-tauri\target\release\cad-studio.exe
```

## Local automation queue

See [the queue protocol](docs/automation-queue-protocol.md).

The desktop client stores jobs in the `queue` folder under the Tauri application-data directory. Run the Python worker once:

```powershell
python -m apps.desktop.cad_workbench.queue_worker --queue-dir "<queue-directory>"
```

Watch continuously:

```powershell
python -m apps.desktop.cad_workbench.queue_worker --watch --queue-dir "<queue-directory>"
```

Normal desktop startup enables the unified Agent handler and does not load mock handlers. The `create_shell`, `import_model`, and `delivery_package` mocks require explicit `--enable-mock`; they are intended for queue-protocol development tests and are not product deliverables.

Enable the unified Agent executor:

```powershell
python -m apps.desktop.cad_workbench.queue_worker --watch --enable-codex --queue-dir "<queue-directory>"
```

The desktop application can start the worker from **Ayarlar (Settings) → Yerel yürütme (Local execution)**. Development builds prefer the current repository; installed builds use bundled skill resources. Stopping the worker terminates the application-managed worker process tree and requeues unfinished tasks. Alt+F4 and system exit perform the same cleanup.

Agent Bridge responsibilities:

- The UI collects configuration, engineering rules, target outputs, and a prompt preview.
- The queue persists JSON jobs and uses `.lock`, leases, stale recovery, quarantine, Worker Health, Artifact Ledger, and Reviewer Gate for reliable local execution.
- The worker validates jobs, enforces Policy Gate and workspace boundaries, fixes output paths, and invokes `codex exec`.
- The selected Agent executes the skill, calls local CAD applications, performs validation, and returns a unified structured result.

Risky capabilities enter `approval_required`, including Git push, `danger-full-access`, CAD macros, external networking, writes outside the workspace, and file deletion. A job returns to `queued` only after approval in the desktop application.

The default Codex sandbox is `workspace-write`. If full access is necessary, approve the job and explicitly start the worker with:

```powershell
python -m apps.desktop.cad_workbench.queue_worker --watch --enable-codex --codex-full-access --queue-dir "<queue-directory>"
```

See [the enterprise Agent control plane](../../docs/agent-framework/enterprise-agent-control-plane.md).
