const { chromium } = require("../apps/workbench-ui/node_modules/playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const repo = path.resolve(__dirname, "..");
const version = JSON.parse(fs.readFileSync(path.join(repo, "apps", "workbench-ui", "src-tauri", "tauri.conf.json"), "utf8")).version;
const portableRoot = process.env.CAD_STUDIO_PORTABLE_ROOT
  || path.join(repo, "release-output", `CAD-Studio-${version}-Windows-x64`);
const executable = path.join(portableRoot, "CAD Studio.exe");
const isolatedHome = path.join(repo, "release-output", "e2e-home");
const queue = path.join(repo, "release-output", "e2e-queue");
const webviewData = path.join(repo, "release-output", "e2e-webview2");
const releaseOutput = path.resolve(repo, "release-output");

/** @brief Restrict end-to-end cleanup scope to avoid removing directories outside the workspace. */
function assertSafeTestPath(target) {
  const resolved = path.resolve(target);
  if (path.dirname(resolved) !== releaseOutput) throw new Error(`Refusing to clean test directory: ${resolved}`);
}

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

/** @brief Wait for readiness with a deadline; report process exit/start failure immediately and retain the last connection error. */
async function waitUntil(check, label, timeout = 90_000, health = () => null) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    const failure = health();
    if (failure) throw new Error(`${label}: ${failure}`);
    try {
      const value = await check();
      if (value) return value;
    } catch (error) { lastError = error; }
    await sleep(250);
  }
  throw new Error(`timeout: ${label}${lastError ? `; last error: ${lastError.message}` : ""}`);
}

/** @brief CDP can connect before WebView2 creates a page or injects the Tauri bridge. */
async function waitForTauriPage(browser, health = () => null, timeout = 90_000) {
  return waitUntil(async () => {
    for (const context of browser.contexts()) {
      for (const page of context.pages()) {
        const ready = await page.evaluate(() => typeof window.__TAURI_INTERNALS__?.invoke === "function");
        if (ready) return page;
      }
    }
    return null;
  }, "portable Tauri page and IPC readiness", timeout, health);
}

async function main() {
  if (!fs.existsSync(executable)) throw new Error(`Portable executable does not exist: ${executable}`);
  [isolatedHome, queue, webviewData].forEach(assertSafeTestPath);
  fs.rmSync(isolatedHome, { recursive: true, force: true });
  fs.rmSync(queue, { recursive: true, force: true });
  fs.rmSync(webviewData, { recursive: true, force: true });
  fs.mkdirSync(isolatedHome, { recursive: true });
  fs.mkdirSync(queue, { recursive: true });

  const app = spawn(executable, [], {
    cwd: portableRoot,
    env: {
      ...process.env,
      CODEX_HOME: path.join(isolatedHome, ".codex"),
      CAD_STUDIO_QUEUE_DIR: queue,
      WEBVIEW2_USER_DATA_FOLDER: webviewData,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: "--remote-debugging-port=9227",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let launchError;
  let output = "";
  const record = (data) => { output = (output + data.toString("utf8")).slice(-32_768); };
  app.stdout.on("data", record);
  app.stderr.on("data", record);
  app.on("error", (error) => { launchError = error; });
  const health = () => launchError?.message
    || (app.exitCode !== null ? `process exited with code ${app.exitCode}` : null)
    || (app.signalCode ? `process exited with signal ${app.signalCode}` : null);
  let browser;
  try {
    await waitUntil(async () => {
      return (await fetch("http://127.0.0.1:9227/json/version", { signal: AbortSignal.timeout(1_000) })).ok;
    }, "portable Tauri CDP start", 90_000, health);
    browser = await chromium.connectOverCDP("http://127.0.0.1:9227");
    const page = await waitForTauriPage(browser, health);
    const invoke = (command, args = {}) => page.evaluate(
      ([activeCommand, activeArgs]) => window.__TAURI_INTERNALS__.invoke(activeCommand, activeArgs),
      [command, args],
    );
    const runtime = await invoke("runtime_health");
    const normalizedRoot = String(runtime.skillRoot || "").replace(/^\\\\\?\\/, "").replace(/\\/g, "/").toLowerCase();
    const expectedRoot = path.join(portableRoot, "skill").replace(/\\/g, "/").toLowerCase();
    if (normalizedRoot !== expectedRoot) {
      throw new Error(`Portable release did not use the adjacent skill: actual=${runtime.skillRoot}, expected=${expectedRoot}`);
    }
    for (const required of [
      "SKILL.md",
      "apps/desktop/cad_workbench/queue_worker.py",
      "apps/desktop/cad_workbench/schemas/automation_job.schema.json",
      "examples/08_mini_fan_motion_assembly.py",
      "mcp-server/server.py",
      "mcp-server/register_all_ai_mcp.ps1",
      "subskills/autocad-automation/SKILL.md",
    ]) {
      if (!fs.existsSync(path.join(portableRoot, "skill", ...required.split("/")))) {
        throw new Error(`Portable release resource missing: ${required}`);
      }
    }
    const started = await invoke("start_worker", { repoPath: "", enableCodex: false, codexFullAccess: false });
    if (!started.running || !started.pid) throw new Error(`Bundled worker failed to start: ${JSON.stringify(started)}`);
    const stopped = await invoke("stop_worker");
    if (stopped.running) throw new Error(`Worker did not stop: ${JSON.stringify(stopped)}`);
    console.log(JSON.stringify({ skillRoot: runtime.skillRoot, python: runtime.python, workerStarted: started, workerStopped: stopped }, null, 2));
  } catch (error) {
    // @brief Record only startup status and own outputs; never dump a process environment containing signing keys.
    fs.writeFileSync(path.join(releaseOutput, "e2e-diagnostics.json"), JSON.stringify({
      executable, pid: app.pid, exitCode: app.exitCode, signalCode: app.signalCode,
      error: error.message, launchError: launchError?.message,
    }, null, 2), "utf8");
    fs.writeFileSync(path.join(releaseOutput, "e2e-diagnostics.log"), output, "utf8");
    throw error;
  } finally {
    if (browser) await browser.close().catch(() => {});
    app.kill("SIGKILL");
  }
}

module.exports = { waitUntil, waitForTauriPage };
if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
