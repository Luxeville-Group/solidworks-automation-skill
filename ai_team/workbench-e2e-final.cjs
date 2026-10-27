const { chromium } = require("../apps/workbench-ui/node_modules/playwright");
const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const repo = path.resolve(__dirname, "..");
const queue = path.join(repo, "ai_team", "workbench-e2e-20260726-final", "queue");
const executable = process.env.CAD_STUDIO_E2E_EXE
  || path.join(repo, "apps", "workbench-ui", "src-tauri", "target", "debug", "cad-studio.exe");
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const readJob = (file) => JSON.parse(fs.readFileSync(path.join(queue, file), "utf8"));
const jobFiles = () => fs.readdirSync(queue).filter((file) => file.startsWith("job-") && file.endsWith(".json"));

async function waitUntil(check, label, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const value = await check();
      if (value) return value;
    } catch {}
    await sleep(250);
  }
  throw new Error(`timeout: ${label}`);
}

async function main() {
  try {
    execFileSync("powershell", ["-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*workbench-e2e-20260726-final*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"]);
  } catch {}
  fs.rmSync(queue, { recursive: true, force: true });
  fs.mkdirSync(queue, { recursive: true });
  const app = spawn(executable, [], {
    cwd: repo,
    env: {
      ...process.env,
      CAD_STUDIO_QUEUE_DIR: queue,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: "--remote-debugging-port=9225",
    },
    stdio: "ignore",
  });

  await waitUntil(async () => {
    try {
      return (await fetch("http://127.0.0.1:9225/json/version")).ok;
    } catch {
      return false;
    }
  }, "CDP start", 15_000);

  const browser = await chromium.connectOverCDP("http://127.0.0.1:9225");
  const page = browser.contexts()[0].pages()[0];
  const browserLogs = [];
  page.on("console", (message) => browserLogs.push(`${message.type()}: ${message.text()}`));
  page.on("pageerror", (error) => browserLogs.push(`pageerror: ${error}`));
  await page.waitForTimeout(4_500);
  const invoke = (command, args = {}) =>
    page.evaluate(([activeCommand, activeArgs]) => window.__TAURI_INTERNALS__.invoke(activeCommand, activeArgs), [command, args]);
  const queuePanel = page.locator(".queue-panel");
  const initial = await page.evaluate(() => ({
    size: [innerWidth, innerHeight],
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    connected: document.body.innerText.includes("Codex Bağlandı"),
    solidworks: document.body.innerText.includes("SolidWorks Kullanılabilir"),
    autocad: document.body.innerText.includes("AutoCAD Kullanılabilir"),
  }));
  const originalSettingsRaw = await page.evaluate(() => localStorage.getItem("cad-studio.settings.v1"));
  const originalChatRaw = await page.evaluate(() => localStorage.getItem("cad-studio.agent-chat.v1"));
  const originalConversationsRaw = await page.evaluate(() => localStorage.getItem("cad-studio.agent-conversations.v1"));

  const originalProjectName = process.env.CAD_STUDIO_E2E_RESTORE_PROJECT
    || await page.locator(".project-name-row strong").innerText();
  const testProjectName = originalProjectName === "Masaüstü etkileşim regresyon projesi" ? "CAD Studio etkileşim regresyonu" : "Masaüstü etkileşim regresyon projesi";
  await page.getByRole("button", { name: "Proje adını değiştir", exact: true }).click();
  const projectNameInput = page.getByRole("textbox", { name: "Proje adı", exact: true });
  await projectNameInput.fill(testProjectName);
  await projectNameInput.press("Enter");
  await waitUntil(
    () => page.evaluate((expected) => JSON.parse(localStorage.getItem("cad-studio.settings.v1") || "{}").projectName === expected, testProjectName),
    "project name persisted",
  );

  await queuePanel.getByRole("button", { name: "Başlat", exact: true }).click();
  let lastWorkerStatus = null;
  let lastWorkerError = null;
  let started;
  try {
    started = await waitUntil(async () => {
      try {
        const status = await invoke("worker_status");
        lastWorkerStatus = status;
        return status.running ? status : false;
      } catch (error) {
        lastWorkerError = String(error);
        return false;
      }
    }, "worker start");
  } catch (error) {
    const healthPath = path.join(queue, "worker_health.json");
    const health = fs.existsSync(healthPath) ? fs.readFileSync(healthPath, "utf8") : null;
    const queueText = page.isClosed() ? "page closed" : await queuePanel.innerText().catch((readError) => String(readError));
    const escapedQueue = queue.replaceAll("'", "''");
    try {
      execFileSync("powershell", ["-NoProfile", "-Command", `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*${escapedQueue}*' -or $_.CommandLine -like '*workbench-e2e-20260726-final*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`]);
    } catch {}
    try {
      app.kill();
    } catch {}
    throw new Error(`${error}; appExit=${app.exitCode}; pageClosed=${page.isClosed()}; lastStatus=${JSON.stringify(lastWorkerStatus)}; lastError=${lastWorkerError}; health=${health}; queue=${queueText}; logs=${browserLogs.join(" | ")}`);
  }

  const firstWorker = started;
  await queuePanel.getByRole("button", { name: "Yürütücüyü yeniden başlat", exact: true }).click();
  const restarted = await waitUntil(async () => {
    const status = await invoke("worker_status");
    return status.running && status.pid !== firstWorker.pid ? status : false;
  }, "worker restart");

  await queuePanel.getByRole("button", { name: "Durdur", exact: true }).click();
  await waitUntil(async () => !(await invoke("worker_status")).running, "worker stop before retry");
  const retryFile = "e2e-retry.json";
  fs.writeFileSync(
    path.join(queue, retryFile),
    JSON.stringify(
      {
        schemaVersion: "1.0",
        id: "e2e-retry",
        runId: "run-e2e-retry-old",
        kind: "codex_task",
        title: "Başarısız görev yeniden deneme testi",
        detail: "Başarısız görevin yeniden kuyruğa alınmasını doğrula",
        status: "failed",
        progress: 100,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        attempt: 1,
        approvedAt: "unix:1",
        approvedBy: "local-user",
        approvedPolicyReasons: ["Onaylandı"],
        error: "Windows Erişim reddedildi",
        result: { message: "Önceki sonuç" },
        artifacts: [{ path: "old.step" }],
        reviewGate: { status: "fail" },
        workerLog: [{ status: "failed", message: "ÖncekiHata" }],
      },
      null,
      2,
    ),
  );
  await page.waitForTimeout(1_700);
  const retryCard = queuePanel.locator(".queue-job").filter({ hasText: "Başarısız görev yeniden deneme testi" }).first();
  await retryCard.getByRole("button", { name: "Yeniden yürüt", exact: true }).click();
  const retried = await waitUntil(() => {
    const value = readJob(retryFile);
    return value.status === "queued" ? value : false;
  }, "failed job retry");
  if (
    retried.runId === "run-e2e-retry-old"
    || retried.progress !== 0
    || retried.error
    || retried.result
    || retried.reviewGate
    || retried.workerLog
    || retried.approvedBy !== "local-user"
  ) {
    throw new Error(`retry state was not reset safely: ${JSON.stringify(retried)}`);
  }
  const retryEvent = fs.readFileSync(path.join(queue, "events", "e2e-retry.jsonl"), "utf8");
  for (const file of [
    path.join(queue, retryFile),
    path.join(queue, "events", "e2e-retry.jsonl"),
    path.join(queue, `${retryFile}.cancel`),
    path.join(queue, `${retryFile}.lock`),
  ]) {
    fs.rmSync(file, { force: true });
  }
  await page.waitForTimeout(1_600);
  started = await waitUntil(async () => {
    const status = await invoke("worker_status");
    return status.running ? status : false;
  }, "worker auto start after retry");

  const recoveryFile = "e2e-recovery.json";
  fs.writeFileSync(
    path.join(queue, recoveryFile),
    JSON.stringify(
      {
        schemaVersion: "1.0",
        id: "e2e-recovery",
        runId: "run-e2e-recovery",
        kind: "codex_task",
        title: "Durdurma kurtarma testi",
        detail: "Worker durdurma kurtarmasını doğrula",
        status: "running",
        progress: 42,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        workerPid: started.pid,
        runnerId: "e2e-runner",
        leaseUntil: "2099-01-01T00:00:00+08:00",
      },
      null,
      2,
    ),
  );
  const cancelledRecoveryFile = "e2e-recovery-cancel.json";
  fs.writeFileSync(
    path.join(queue, cancelledRecoveryFile),
    JSON.stringify(
      {
        schemaVersion: "1.0",
        id: "e2e-recovery-cancel",
        runId: "run-e2e-recovery-cancel",
        kind: "codex_task",
        title: "Durdurma sırasında iptal testi",
        detail: "Worker dururken bağımsız iptal işaretinin korunduğunu doğrula",
        status: "running",
        progress: 42,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        workerPid: started.pid,
        runnerId: "e2e-runner",
        leaseUntil: "2099-01-01T00:00:00+08:00",
      },
      null,
      2,
    ),
  );
  fs.writeFileSync(path.join(queue, `${cancelledRecoveryFile}.cancel`), "cancel\n");
  await page.waitForTimeout(1_700);
  await queuePanel.getByRole("button", { name: "Durdur", exact: true }).click();
  await waitUntil(() => readJob(recoveryFile).status === "queued", "running job requeued");
  await waitUntil(() => readJob(cancelledRecoveryFile).status === "cancelled", "cancel marker preserved during stop");
  const recovered = readJob(recoveryFile);
  const cancelledRecovery = readJob(cancelledRecoveryFile);
  const recoveryEvent = fs.readFileSync(path.join(queue, "events", "e2e-recovery.jsonl"), "utf8");
  const cancelledRecoveryEvent = fs.readFileSync(path.join(queue, "events", "e2e-recovery-cancel.jsonl"), "utf8");
  for (const file of [
    path.join(queue, recoveryFile),
    path.join(queue, "events", "e2e-recovery.jsonl"),
    path.join(queue, "e2e-recovery.json.lock"),
    path.join(queue, cancelledRecoveryFile),
    path.join(queue, `${cancelledRecoveryFile}.cancel`),
    path.join(queue, "events", "e2e-recovery-cancel.jsonl"),
    path.join(queue, "e2e-recovery-cancel.json.lock"),
  ]) {
    fs.rmSync(file, { force: true });
  }
  await page.waitForTimeout(1_600);

  await page.getByRole("button", { name: "Modelleme", exact: true }).click();
  const beforeTemplateFiles = jobFiles();
  await page.locator(".capability-card").filter({ hasText: "Genel parça" }).first().click();
  await page.waitForTimeout(800);
  const afterTemplateFiles = jobFiles();
  if (afterTemplateFiles.length !== beforeTemplateFiles.length) {
    throw new Error(`template click created a queue job: ${JSON.stringify(afterTemplateFiles)}`);
  }
  const selectedTemplate = await page.locator(".capability-card.selected").filter({ hasText: "Genel parça" }).first().innerText();
  await page.locator(".bridge-run").click();
  const createdFile = await waitUntil(
    () => jobFiles().find((file) => !beforeTemplateFiles.includes(file)),
    "confirmed template job file",
  );
  await waitUntil(() => readJob(createdFile).status === "approval_required", "policy approval");
  await queuePanel.getByRole("button", { name: "Durdur", exact: true }).click();
  const createdId = readJob(createdFile).id;
  const createdCard = queuePanel.locator(".queue-job").filter({ hasText: "Genel parça" }).first();
  await createdCard.getByRole("button", { name: "Onayla", exact: true }).click();
  await waitUntil(() => readJob(createdFile).status === "queued", "approved queued");
  await createdCard.getByRole("button", { name: "İptal", exact: true }).click();
  await waitUntil(() => readJob(createdFile).status === "cancelled", "queued cancelled");
  const createdStatusBeforeDelete = readJob(createdFile).status;
  const projectMenuTrigger = page.getByRole("button", { name: /Proje değiştir; mevcut: / });
  if (await projectMenuTrigger.getAttribute("aria-expanded") === "true") await projectMenuTrigger.click();
  const sidebarCreatedItem = page.locator(".project-sequence-item").filter({ hasText: "Genel parça" }).first();
  await sidebarCreatedItem.locator(".project-sequence-delete").click();
  await sidebarCreatedItem.locator(".project-sequence-delete.confirm").click();
  await waitUntil(() => !fs.existsSync(path.join(queue, createdFile)), "cancelled job deleted");

  const artifact = path.join(queue, "e2e-model.step");
  fs.writeFileSync(artifact, "ISO-10303-21;\nEND-ISO-10303-21;\n");
  const reviewFile = "e2e-review.json";
  fs.writeFileSync(
    path.join(queue, reviewFile),
    JSON.stringify(
      {
        schemaVersion: "1.0",
        id: "e2e-review",
        runId: "run-e2e-review",
        kind: "codex_task",
        title: "İnsan incelemesi testi",
        detail: "İnceleme kanıtı sürecini doğrula",
        status: "review_required",
        progress: 100,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        expectedOutput: "STEP",
        artifacts: [
          {
            kind: "step",
            path: artifact,
            exists: true,
            sizeBytes: 42,
            sha256: "e2e-sha",
            producedThisRun: true,
          },
        ],
        reviewGate: {
          status: "warning",
          checks: [{ id: "native-open", status: "warning", severity: "P1", message: "Yerel CAD uygulamasında açıp incelemek gerekli" }],
        },
      },
      null,
      2,
    ),
  );
  await page.waitForTimeout(1_900);
  const sidebarReviewItem = page.locator(".project-sequence-item").filter({ hasText: "İnsan incelemesi testi" }).first();
  const sidebarReviewText = await sidebarReviewItem.innerText();
  if (!sidebarReviewText.includes("Tamamlandı · 100%") || sidebarReviewText.includes("İnceleme bekliyor")) {
    throw new Error(`sidebar completion label is incorrect: ${sidebarReviewText}`);
  }
  let manualReviewBypassRejected = false;
  try {
    await invoke("approve_review_job", {
      id: "e2e-review",
      reason: "Rastgele kontrol öğeleriyle insan incelemesi backend doğrulamasını atlama denemesi.",
      checks: ["one", "two", "three"],
    });
  } catch (error) {
    manualReviewBypassRejected = String(error).includes("tüm insan kontrol öğeleri");
  }
  if (!manualReviewBypassRejected || readJob(reviewFile).status !== "review_required") {
    throw new Error("manual review backend accepted an incomplete checklist");
  }
  await page.getByRole("button", { name: /İnsan incelemesi testi/ }).first().click();
  const form = page.locator(".manual-review-form");
  await form.waitFor({ state: "visible" });
  for (const checkbox of await form.locator('input[type="checkbox"]').all()) await checkbox.check();
  await waitUntil(
    async () => {
      const checked = await form.locator('input[type="checkbox"]:checked').count();
      const total = await form.locator('input[type="checkbox"]').count();
      return checked === total;
    },
    "manual review checklist state",
  );
  await form
    .locator("textarea")
    .fill("SOLIDWORKS içinde açıldı; kritik ölçüler, gerçek delik/slot özellikleri ve STEP dosya sürümü denetlendi; sorun bulunamadı.");
  const approveReviewButton = form.getByRole("button", { name: "İnceleme geçti", exact: true });
  await waitUntil(() => approveReviewButton.isEnabled(), "manual review action enabled");
  await approveReviewButton.click();
  const reviewed = await waitUntil(
    () => {
      const job = readJob(reviewFile);
      return job.status === "passed" ? job : false;
    },
    "manual review pass",
  );

  let duplicateRejected = false;
  try {
    await invoke("save_queue_job", { job: { ...reviewed, status: "queued" } });
  } catch (error) {
    duplicateRejected = String(error).includes("Job already exists");
  }

  const tabResults = {};
  for (const label of ["Genel bakış", "Modelleme", "Özellik (feature)", "Çizim", "İncele", "Teslim", "Ayarlar", "Yardım"]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await page.waitForTimeout(120);
    tabResults[label] = await page.evaluate(() => ({
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      heading: document.querySelector(".project-title strong")?.textContent,
    }));
  }
  await page.getByRole("button", { name: "Genel bakış", exact: true }).click();

  const conversationSelect = page.getByLabel("Değiştir AI Konuşma", { exact: true });
  await page.getByLabel("Seç AI Sağlayıcı", { exact: true }).selectOption("codex");
  await page.getByRole("button", { name: "Yeni AI Konuşma", exact: true }).click();
  const firstConversationId = await conversationSelect.inputValue();
  await page.getByLabel("Konuşma modelini seç", { exact: true }).selectOption("gpt-5.6-sol");
  await page.getByRole("button", { name: "Yeni AI Konuşma", exact: true }).click();
  const secondConversationId = await conversationSelect.inputValue();
  await page.getByLabel("Konuşma modelini seç", { exact: true }).selectOption("gpt-5.6-terra");
  await conversationSelect.selectOption(firstConversationId);
  const conversationIsolation = {
    separateIds: firstConversationId !== secondConversationId,
    firstModelRestored: await page.getByLabel("Konuşma modelini seç", { exact: true }).inputValue() === "gpt-5.6-sol",
    providerLabel: await page.getByLabel("Seç AI Sağlayıcı", { exact: true }).locator("option:checked").innerText(),
  };

  await page.getByRole("button", { name: new RegExp(`Proje değiştir; mevcut:  ${testProjectName}`) }).click();
  await page.getByRole("menuitem", { name: "Yeni proje", exact: true }).click();
  await page.getByRole("textbox", { name: "Proje adı", exact: true }).fill("Proje değiştirme regresyonu");
  await page.getByRole("textbox", { name: "Proje adı", exact: true }).press("Enter");
  await waitUntil(() => page.locator(".project-sequence-item").count().then((count) => count === 0), "new project starts empty");
  await page.getByRole("button", { name: /Proje değiştir; mevcut:  Proje değiştirme regresyonu/ }).click();
  await page.getByRole("menuitem", { name: new RegExp(testProjectName) }).click();
  await page.locator(".project-sequence-item").filter({ hasText: "İnsan incelemesi testi" }).first().waitFor({ state: "visible" });
  await page.getByRole("button", { name: new RegExp(`Proje değiştir; mevcut:  ${testProjectName}`) }).click();
  await page.getByRole("menuitem", { name: /Proje değiştirme regresyonu/ }).click();
  await waitUntil(() => page.locator(".project-sequence-item").count().then((count) => count === 0), "switched project remains empty");
  await page.getByRole("button", { name: /Proje değiştir; mevcut:  Proje değiştirme regresyonu/ }).click();
  await page.getByRole("button", { name: "Projeyi sil Proje değiştirme regresyonu", exact: true }).click();
  await page.getByRole("button", { name: "Proje silmeyi onayla Proje değiştirme regresyonu", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(`Proje değiştir; mevcut:  ${testProjectName}`) }).waitFor({ state: "visible" });
  await page.locator(".project-sequence-item").filter({ hasText: "İnsan incelemesi testi" }).first().waitFor({ state: "visible" });
  await page.getByRole("button", { name: new RegExp(`Proje değiştir; mevcut:  ${testProjectName}`) }).click();
  const deletedProjectAbsent = await page.getByRole("menuitem", { name: /Proje değiştirme regresyonu/ }).count() === 0;
  await page.keyboard.press("Escape");
  const projectSwitch = {
    newProjectEmpty: true,
    restoredProject: await page.locator(".project-switcher-trigger strong").innerText(),
    deletedProjectAbsent,
  };
  await page.screenshot({ path: path.join(repo, "ai_team", "ui_review", "final-e2e-desktop.png") });

  const verifiedProjectName = await page.locator(".project-name-row strong").innerText();
  await page.getByRole("button", { name: "Proje adını değiştir", exact: true }).click();
  await page.getByRole("textbox", { name: "Proje adı", exact: true }).fill(originalProjectName);
  await page.getByRole("textbox", { name: "Proje adı", exact: true }).press("Enter");
  await waitUntil(
    () => page.evaluate((expected) => JSON.parse(localStorage.getItem("cad-studio.settings.v1") || "{}").projectName === expected, originalProjectName),
    "project name restored",
  );

  const wallpaperSource = path.join(repo, "apps", "workbench-ui", "src-tauri", "icons", "128x128.png");
  const importedWallpaper = await invoke("import_wallpaper", { sourcePath: wallpaperSource });
  const customWallpaperLayer = page.locator(".app-shell.theme-custom div.custom-wallpaper-layer").first();
  let wallpaperDiagnostics;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.waitForTimeout(attempt === 0 ? 600 : 2_500);
    await Promise.all([
      page.waitForNavigation({ waitUntil: "domcontentloaded" }),
      page.evaluate((wallpaper) => {
        const settings = JSON.parse(localStorage.getItem("cad-studio.settings.v1") || "{}");
        settings.activeWallpaper = "custom";
        settings.customWallpaperPath = wallpaper.path;
        localStorage.setItem("cad-studio.settings.v1", JSON.stringify(settings));
        location.reload();
      }, importedWallpaper),
    ]);
    if (await customWallpaperLayer.waitFor({ state: "visible", timeout: 15_000 }).then(() => true).catch(() => false)) break;
    wallpaperDiagnostics = await page.evaluate(() => ({
      shellClass: document.querySelector(".app-shell")?.className,
      settings: JSON.parse(localStorage.getItem("cad-studio.settings.v1") || "{}"),
      hint: document.querySelector(".window-hint")?.textContent,
      layers: Array.from(document.querySelectorAll(".custom-wallpaper-layer")).map((element) => ({
        tag: element.tagName,
        style: element.getAttribute("style"),
        backgroundImage: getComputedStyle(element).backgroundImage,
      })),
    }));
  }
  if (!(await customWallpaperLayer.isVisible())) {
    throw new Error(`custom wallpaper did not become visible; wallpaper=${JSON.stringify(wallpaperDiagnostics)}; logs=${browserLogs.join(" | ")}`);
  }
  const wallpaperBackground = await customWallpaperLayer.evaluate((element) => getComputedStyle(element).backgroundImage);
  if (!wallpaperBackground || wallpaperBackground === "none") {
    throw new Error(`custom wallpaper did not render: ${wallpaperBackground}`);
  }
  const wallpaper = {
    cached: fs.existsSync(importedWallpaper.path),
    rendered: wallpaperBackground !== "none",
    kind: importedWallpaper.kind,
  };
  conversationIsolation.modelAfterReload = await page.getByLabel("Konuşma modelini seç", { exact: true }).inputValue() === "gpt-5.6-sol";

  const result = {
    initial,
    started,
    restarted: {
      firstPid: firstWorker.pid,
      nextPid: restarted.pid,
      changed: firstWorker.pid !== restarted.pid,
    },
    retried: {
      status: retried.status,
      progress: retried.progress,
      runIdChanged: retried.runId !== "run-e2e-retry-old",
      approvalPreserved: retried.approvedBy === "local-user",
      event: retryEvent.includes("run.requeued_by_user"),
    },
    recovered: {
      status: recovered.status,
      runnerId: recovered.runnerId,
      workerPid: recovered.workerPid,
      event: recoveryEvent.includes("run.requeued_worker_stopped"),
      cancelledStatus: cancelledRecovery.status,
      cancelledEvent: cancelledRecoveryEvent.includes("run.cancelled"),
    },
    projectName: { verified: verifiedProjectName, restored: originalProjectName },
    projectSwitch,
    conversationIsolation,
    wallpaper,
    settingsRestored: false,
    template: {
      selected: selectedTemplate.includes("Ayarlar yüklendi"),
      createdOnSelect: afterTemplateFiles.length !== beforeTemplateFiles.length,
      createdAfterConfirm: Boolean(createdFile),
    },
    created: { id: createdId, statusBeforeDelete: createdStatusBeforeDelete, deleted: !fs.existsSync(path.join(queue, createdFile)) },
    sidebarReviewText,
    reviewed: {
      status: reviewed.status,
      decision: reviewed.reviewDecision,
      note: reviewed.reviewNote,
      checks: reviewed.reviewGate?.manualReview?.checks?.length,
      evidence: reviewed.reviewGate?.manualReview?.artifacts?.length,
    },
    duplicateRejected,
    manualReviewBypassRejected,
    tabResults,
  };

  result.settingsRestored = await page.evaluate((original) => {
    for (const [key, raw] of Object.entries(original)) {
      if (raw === null) localStorage.removeItem(key);
      else localStorage.setItem(key, raw);
    }
    const restored = Object.entries(original).every(([key, raw]) => localStorage.getItem(key) === raw);
    void window.__TAURI_INTERNALS__.invoke("plugin:window|close", { label: "main" });
    return restored;
  }, {
    "cad-studio.settings.v1": originalSettingsRaw,
    "cad-studio.agent-chat.v1": originalChatRaw,
    "cad-studio.agent-conversations.v1": originalConversationsRaw,
  }).catch((error) => {
    if (String(error).includes("Target page, context or browser has been closed")) return true;
    throw error;
  });
  await waitUntil(() => app.exitCode !== null, "app exit", 10_000);
  result.closed = { exitCode: app.exitCode };
  const escapedExecutable = executable.replaceAll("'", "''");
  const escapedQueue = queue.replaceAll("'", "''");
  result.remainingWorkers = execFileSync(
    "powershell",
    ["-NoProfile", "-Command", `@(
      Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq 'cad-studio.exe' -and $_.ExecutablePath -eq '${escapedExecutable}') -or
        ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*queue_worker.py*' -and $_.CommandLine -like '*${escapedQueue}*')
      }
    ).Count`],
    { encoding: "utf8" },
  ).trim();
  console.log(JSON.stringify(result, null, 2));
}

main().then(() => process.exit(0)).catch((error) => {
  console.error(error);
  process.exit(1);
});
