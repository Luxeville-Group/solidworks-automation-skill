/** @file delivery-gate-e2e.cjs
 *  @brief Validate delivery gates, version history, and responsive layout with real Chromium.
 */
const { chromium } = require("../apps/workbench-ui/node_modules/playwright");
const fs = require("fs");
const http = require("http");
const path = require("path");

const repo = path.resolve(__dirname, "..");
const dist = path.join(repo, "apps", "workbench-ui", "dist");
const output = path.join(repo, "output", "playwright", "delivery-gate");
const queueKey = "cad-studio.queue.v1";
const mimeTypes = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".webp": "image/webp", ".mp4": "video/mp4" };

function testJob(status = "review_required") {
  const now = "2026-08-01T19:40:00+08:00";
  const manualReviewRequired = status !== "passed";
  return {
    schemaVersion: "2.0",
    id: "delivery-gate-e2e",
    runId: "run-current",
    kind: "delivery_package",
    title: "Montaj plakasıMühendislik çizimiTeslim",
    detail: "Validate model, drawing, BOM, preview, and review-report delivery traceability",
    status,
    progress: 100,
    createdAt: now,
    updatedAt: now,
    requestedBy: "e2e",
    createdByAppVersion: "0.3.1",
    projectId: "project-default",
    expectedOutput: "STEP / DWG / BOM / PNG / İnceleme raporu",
    requiredArtifacts: ["model", "drawing", "bom", "preview", "report"],
    artifacts: [
      { kind: "model", path: "D:/delivery/v2/install-plate.step", exists: true, producedThisRun: true, sizeBytes: 12000, sha256: "model-v2" },
      { kind: "drawing", path: "D:/delivery/v2/install-plate.dwg", exists: true, producedThisRun: true, sizeBytes: 37000, sha256: "drawing-v2" },
      { kind: "bom", path: "D:/delivery/v2/install-plate-bom.csv", exists: true, producedThisRun: true, sizeBytes: 960, sha256: "bom-v2" },
      { kind: "preview", path: "D:/delivery/v2/install-plate.png", exists: true, producedThisRun: true, sizeBytes: 19000, sha256: "preview-v2" },
      { kind: "report", path: "D:/delivery/v2/review-report.json", exists: true, producedThisRun: true, sizeBytes: 2400, sha256: "report-v2" },
    ],
    artifactLedgerPath: "D:/delivery/v2/artifact-ledger.json",
    reviewGatePath: "D:/delivery/v2/review-report.json",
    reviewGate: { status: manualReviewRequired ? "warning" : "pass", checks: [{ id: "artifacts", status: "pass", message: "Bu çalıştırmanın çıktıları eksiksiz" }] },
    drawingEvidence: { status: "pass", stage: "review", manual_review_required: manualReviewRequired },
    bomEvidence: { status: "pass", stage: "review", manual_review_required: manualReviewRequired },
    artifactRelations: [
      { from: "D:/delivery/v2/install-plate.step", to: "D:/delivery/v2/install-plate.dwg", type: "OluşturMühendislik çizimi" },
      { from: "D:/delivery/v2/install-plate.dwg", to: "D:/delivery/v2/install-plate.png", type: "Dışa aktarÖnizleme" },
    ],
    backendDiagnostics: {
      autocad_dotnet: { backend: "autocad_dotnet", status: "pilot", stage: "review", limitations: ["AutoCAD 2024 allowlisted commands"] },
      autocad_com: { backend: "autocad_com", status: "blocked", stage: "preflight", error_code: "AUTOCAD_COM_UNSTABLE" },
    },
    runHistory: [{
      runId: "run-v1",
      status: "failed",
      updatedAt: "2026-08-01T18:30:00+08:00",
      artifacts: [
        { kind: "model", path: "D:/delivery/v1/install-plate.step", exists: true, producedThisRun: true, sha256: "model-v1" },
        { kind: "drawing", path: "D:/delivery/v1/install-plate.dwg", exists: true, producedThisRun: true, sha256: "drawing-v1" },
        { kind: "report", path: "D:/delivery/v1/legacy-review-report.json", exists: true, producedThisRun: true, sha256: "legacy-report-v1" },
      ],
      error: "Mühendislik çizimiÖlçülerGerekliİncele",
    }],
    retryPolicy: { previousRunId: "run-v1", retryFromStage: "drawing-bom", scope: "failed_stage_and_downstream", preservePreviousArtifacts: true, overwrite: false },
    reviewDecision: status === "passed" ? "approved" : undefined,
  };
}

function createServer() {
  return http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
    const relative = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
    const target = path.resolve(dist, relative);
    if (!target.startsWith(path.resolve(dist)) || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
      response.writeHead(404).end("not found");
      return;
    }
    response.writeHead(200, { "Content-Type": `${mimeTypes[path.extname(target)] || "application/octet-stream"}; charset=utf-8` });
    fs.createReadStream(target).pipe(response);
  });
}

async function inspect(page, baseUrl, width, height, status, screenshotName, mutateJob) {
  await page.setViewportSize({ width, height });
  const job = testJob(status);
  mutateJob?.(job);
  await page.addInitScript(([key, value]) => localStorage.setItem(key, JSON.stringify([value])), [queueKey, job]);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const deliveryButton = page.getByRole("button", { name: "Teslim", exact: true });
  await deliveryButton.waitFor({ state: "visible", timeout: 15_000 });
  await deliveryButton.click();
  await page.locator(".delivery-gate").waitFor({ state: "visible" });
  await page.screenshot({ path: path.join(output, screenshotName), fullPage: true });
  return page.evaluate(() => ({
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    disposition: [...document.querySelector(".delivery-gate")?.classList || []],
    gateText: document.querySelector(".delivery-gate")?.textContent || "",
    retryText: document.querySelector(".delivery-heading-actions")?.textContent || "",
    versionText: document.querySelector(".delivery-versions")?.textContent || "",
    diagnosticText: document.querySelector(".delivery-diagnostics")?.textContent || "",
    traceRows: document.querySelectorAll(".delivery-trace-row").length,
    previewCount: document.querySelectorAll(".cad-preview").length,
  }));
}

async function main() {
  if (!fs.existsSync(path.join(dist, "index.html"))) throw new Error("Önce çalıştırın:  npm run build");
  fs.mkdirSync(output, { recursive: true });
  const server = createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Cannot obtain the temporary UI port");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const desktop = await inspect(await context.newPage(), baseUrl, 1440, 900, "review_required", "delivery-review-1440x900.png");
    const compact = await inspect(await context.newPage(), baseUrl, 760, 900, "passed", "delivery-ready-760x900.png");
    const incomplete = await inspect(await context.newPage(), baseUrl, 1024, 800, "passed", "delivery-incomplete-1024x800.png", (job) => {
      job.artifacts = job.artifacts.filter((artifact) => artifact.kind !== "bom");
    });
    const result = { desktop, compact, incomplete };
    fs.writeFileSync(path.join(output, "metrics.json"), JSON.stringify(result, null, 2));
    if (desktop.overflowX || compact.overflowX) throw new Error("Delivery page has horizontal overflow");
    if (!desktop.disposition.includes("review_required") || !desktop.gateText.includes("İnsan incelemesi bekleniyor")) throw new Error("Review-required gate was not displayed correctly");
    if (desktop.gateText.includes("Bu yürütme teslim edilebilir")) throw new Error("Review-required task was incorrectly marked deliverable");
    if (!desktop.retryText.includes("Mühendislik çizimi ve BOM aşamasından yeniden üret")) throw new Error("Partial rerun stage was not displayed");
    if (!desktop.versionText.includes("run-v1") || !desktop.diagnosticText.includes("AUTOCAD_COM_UNSTABLE")) throw new Error("Version or backend diagnostics missing");
    if (!desktop.versionText.includes("Sil 1")) throw new Error("Deleted artifacts were not counted correctly in version history");
    if (!compact.disposition.includes("ready") || !compact.gateText.includes("Bu yürütme teslim edilebilir")) throw new Error("Approved task was not shown as deliverable");
    if (!incomplete.disposition.includes("incomplete") || !incomplete.gateText.includes("Gerekli çıktı eksik: bom")) throw new Error("Task missing a BOM was incorrectly marked deliverable");
    if (desktop.traceRows !== 2 || compact.traceRows !== 2) throw new Error("Artifact relationships were not displayed completely");
    if (desktop.previewCount !== 1 || compact.previewCount !== 1) throw new Error("Delivery page rendered a duplicate file preview");
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
