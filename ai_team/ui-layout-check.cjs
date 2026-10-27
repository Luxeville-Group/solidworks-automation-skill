const { chromium } = require("../apps/workbench-ui/node_modules/playwright");
const path = require("path");

const repo = path.resolve(__dirname, "..");
const output = path.join(repo, "ai_team", "ui_review");
const baseUrl = process.env.CAD_STUDIO_UI_URL || "http://127.0.0.1:5174";

async function inspect(page, width, height, filename) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => localStorage.clear());
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(output, filename), fullPage: false });

  return page.evaluate(() => {
    const rect = (selector) => {
      const box = document.querySelector(selector)?.getBoundingClientRect();
      return box ? { top: Math.round(box.top), bottom: Math.round(box.bottom), height: Math.round(box.height) } : null;
    };
    return {
      viewport: [innerWidth, innerHeight],
      documentHeight: document.documentElement.scrollHeight,
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      theme: document.querySelector(".app-shell")?.className,
      wallpaperVideo: (() => {
        const video = document.querySelector(".custom-wallpaper-video");
        return video ? { readyState: video.readyState, paused: video.paused, currentSrc: video.currentSrc } : null;
      })(),
      dock: rect(".dock-panel"),
      main: rect(".main-window"),
      toolbar: rect(".app-toolbar"),
      firstWorkspace: rect(".main-window > :nth-child(2)"),
    };
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  const result = {
    desktop: await inspect(page, 1180, 760, "final-1180x760.png"),
    compact: await inspect(page, 760, 900, "final-760x900.png"),
  };
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.setViewportSize({ width: 1180, height: 760 });
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  const wallpaperVideo = page.locator(".custom-wallpaper-video");
  const hasVideo = (await wallpaperVideo.count()) > 0;
  const startTime = hasVideo ? await wallpaperVideo.evaluate((video) => video.currentTime) : null;
  await page.waitForTimeout(900);
  const endTime = hasVideo ? await wallpaperVideo.evaluate((video) => video.currentTime) : null;
  await page.screenshot({ path: path.join(output, "final-wallpaper-motion.png"), fullPage: false });
  result.motion = { startTime, endTime, advanced: hasVideo ? endTime > startTime : null };

  const settings = {};
  for (const [name, width, height] of [
    ["desktop", 1180, 760],
    ["compact", 760, 900],
  ]) {
    await page.setViewportSize({ width, height });
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Ayarlar", exact: true }).click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(output, `final-settings-${name}.png`), fullPage: false });
    await page.locator(".knowledge-setting").scrollIntoViewIfNeeded();
    await page.locator(".knowledge-setting").getByRole("button", { name: "Bulut desteği", exact: true }).click();
    await page.waitForTimeout(180);
    await page.screenshot({ path: path.join(output, `final-settings-knowledge-${name}.png`), fullPage: false });
    settings[name] = await page.evaluate(() => {
      const knowledge = document.querySelector(".knowledge-setting")?.getBoundingClientRect();
      const fields = [...document.querySelectorAll(".setting-card input")].map((element) => {
        const box = element.getBoundingClientRect();
        return { width: box.width, scrollWidth: element.scrollWidth, visible: box.width > 0 && box.height > 0 };
      });
      return {
        overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        documentHeight: document.documentElement.scrollHeight,
        knowledgeVisible: Boolean(knowledge && knowledge.width > 0 && knowledge.height > 0),
        clippedInputs: fields.some((field) => field.visible && field.scrollWidth > field.width + 2),
      };
    });
  }

  result.help = {};
  for (const [name, width, height] of [
    ["desktop", 1180, 760],
    ["compact", 760, 900],
  ]) {
    await page.setViewportSize({ width, height });
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Yardım", exact: true }).click();
    await page.waitForTimeout(200);
    await page.screenshot({ path: path.join(output, `final-help-${name}.png`), fullPage: false });
    result.help[name] = await page.evaluate(() => {
      const workspace = document.querySelector(".help-workspace");
      const steps = [...document.querySelectorAll(".help-steps li")];
      const viewportWidth = document.documentElement.clientWidth;
      return {
        visible: Boolean(workspace && workspace.getBoundingClientRect().height > 0),
        overflowX: document.documentElement.scrollWidth > viewportWidth,
        clippedSteps: steps.some((step) => {
          const box = step.getBoundingClientRect();
          return box.left < -1 || box.right > viewportWidth + 1 || step.scrollWidth > step.clientWidth + 1;
        }),
      };
    });
  }
  result.settings = settings;

  await page.setViewportSize({ width: 1180, height: 760 });
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.getByRole("button", { name: "Görünüm", exact: true }).click();
  const appearance = page.locator(".appearance-popover");
  await appearance.waitFor({ state: "visible" });
  const appearanceMetrics = await appearance.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));

  result.wallpapers = {};
  for (const [name, theme] of [
    ["Fuji Alacakaranlığı", "theme-fuji"],
    ["Mavi Gökyüzü", "theme-anime-sky"],
    ["Tokyo Neon", "theme-tokyo-neon"],
  ]) {
    await appearance.getByRole("button", { name: new RegExp(name) }).click();
    await page.waitForTimeout(820);
    await page.screenshot({ path: path.join(output, `wallpaper-${theme}.png`), fullPage: false });
    result.wallpapers[name] = await page.evaluate((expectedTheme) => {
      const layers = document.querySelectorAll(".preset-wallpaper-layer");
      const layer = layers.item(layers.length - 1);
      return {
        themeApplied: document.querySelector(".app-shell")?.classList.contains(expectedTheme),
        backgroundImage: layer ? getComputedStyle(layer).backgroundImage : "",
      };
    }, theme);
  }

  await appearance.getByRole("radio", { name: "Sinematik kamera", exact: true }).click();
  const camera = page.locator(".wallpaper-camera");
  await page.waitForTimeout(120);
  const shotBefore = await camera.evaluate((element) => ({
    x: element.style.getPropertyValue("--wallpaper-camera-x"),
    y: element.style.getPropertyValue("--wallpaper-camera-y"),
    scale: element.style.getPropertyValue("--wallpaper-camera-scale"),
  }));
  await appearance.getByRole("button", { name: "Yakın görünüşü değiştir", exact: true }).click();
  await page.waitForTimeout(120);
  const shotAfter = await camera.evaluate((element) => ({
    x: element.style.getPropertyValue("--wallpaper-camera-x"),
    y: element.style.getPropertyValue("--wallpaper-camera-y"),
    scale: element.style.getPropertyValue("--wallpaper-camera-scale"),
  }));

  await appearance.getByRole("radio", { name: "İşaretçiyi izle", exact: true }).click();
  await page.mouse.move(40, 40);
  await page.waitForTimeout(260);
  const pointerA = await camera.evaluate((element) => getComputedStyle(element).transform);
  await page.mouse.move(1120, 700);
  await page.waitForTimeout(260);
  const pointerB = await camera.evaluate((element) => getComputedStyle(element).transform);
  result.wallpaperInteraction = {
    appearanceMetrics,
    shotChanged: JSON.stringify(shotBefore) !== JSON.stringify(shotAfter),
    pointerChanged: pointerA !== pointerB,
  };

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload({ waitUntil: "networkidle" });
  const reducedCamera = page.locator(".wallpaper-camera");
  result.reducedMotion = await reducedCamera.evaluate((element) => ({
    modeStill: element.classList.contains("motion-still"),
    animationName: getComputedStyle(element).animationName,
  }));
  await browser.close();

  if (result.desktop.overflowX || result.compact.overflowX) throw new Error("Horizontal overflow detected");
  if (result.compact.toolbar?.top >= result.compact.viewport[1]) throw new Error("Compact toolbar is outside the initial viewport");
  if (!result.motion.advanced) throw new Error("Default animated wallpaper did not advance");
  if (result.settings.desktop.overflowX || result.settings.compact.overflowX) throw new Error("Settings page has horizontal overflow");
  if (!result.help.desktop.visible || !result.help.compact.visible) throw new Error("Help page was not displayed correctly");
  if (result.help.desktop.overflowX || result.help.compact.overflowX) throw new Error("Help page has horizontal overflow");
  if (result.help.desktop.clippedSteps || result.help.compact.clippedSteps) throw new Error("Help steps are clipped");
  if (!result.settings.desktop.knowledgeVisible || !result.settings.compact.knowledgeVisible) throw new Error("Knowledge-base settings were not displayed correctly");
  if (result.settings.desktop.clippedInputs || result.settings.compact.clippedInputs) throw new Error("Knowledge-base input content is clipped");
  if (result.wallpaperInteraction.appearanceMetrics.overflowY !== "auto") throw new Error("Appearance dialog does not scroll independently");
  for (const [name, wallpaper] of Object.entries(result.wallpapers)) {
    if (!wallpaper.themeApplied || !wallpaper.backgroundImage.includes("url(")) throw new Error(`${name} wallpaper was not loaded`);
  }
  if (!result.wallpaperInteraction.shotChanged) throw new Error("Changing the close view did not change the camera transform");
  if (!result.wallpaperInteraction.pointerChanged) throw new Error("Pointer tracking did not change the camera transform");
  if (!result.reducedMotion.modeStill) throw new Error("Reduced-motion preference did not switch wallpaper to still mode");
  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
