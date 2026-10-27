/** @brief Verify portable waiter transient-connection retries and startup failure diagnostics without running the desktop app. */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { runInNewContext } = require("node:vm");
const { waitUntil, waitForTauriPage } = require("../ai_team/release-portable-e2e.cjs");

test("Retry until connected and return the actual ready value", async () => {
  let calls = 0;
  const value = await waitUntil(() => {
    if (++calls === 1) throw new Error("ECONNREFUSED");
    return "ready";
  }, "fixture", 1_000);
  assert.equal(value, "ready");
  assert.equal(calls, 2);
});

test("Fail immediately on early process exit without waiting for a port timeout", async () => {
  await assert.rejects(waitUntil(() => assert.fail("Do not keep checking the port after process exit"), "fixture", 1_000,
    () => "process exited with code 7"), /process exited with code 7/);
});

test("Timeout preserves the last connection error and cannot pass", async () => {
  await assert.rejects(waitUntil(() => { throw new Error("ECONNREFUSED"); }, "fixture", 10),
    /timeout: fixture; last error: ECONNREFUSED/);
});

test("Wait for a context and delayed page creation after CDP connects", async () => {
  let contextCalls = 0;
  let pageCalls = 0;
  const page = { evaluate: async () => true };
  const context = { pages: () => ++pageCalls === 1 ? [] : [page] };
  const browser = { contexts: () => ++contextCalls === 1 ? [] : [context] };

  assert.equal(await waitForTauriPage(browser, () => null, 2_000), page);
  assert.equal(contextCalls, 3);
  assert.equal(pageCalls, 2);
});

test("Wait for the Tauri invoke function after the page exists", async () => {
  const windows = [{}, { __TAURI_INTERNALS__: {} }, { __TAURI_INTERNALS__: { invoke() {} } }];
  let evaluations = 0;
  const page = {
    evaluate: async (predicate) => runInNewContext(`(${predicate.toString()})()`, { window: windows[evaluations++] }),
  };
  const browser = { contexts: () => [{ pages: () => [page] }] };

  assert.equal(await waitForTauriPage(browser, () => null, 2_000), page);
  assert.equal(evaluations, 3);
});

test("Retry a transient page navigation failure while awaiting Tauri readiness", async () => {
  let evaluations = 0;
  const page = {
    evaluate: async () => {
      if (++evaluations === 1) throw new Error("Execution context was destroyed");
      return true;
    },
  };
  const browser = { contexts: () => [{ pages: () => [page] }] };

  assert.equal(await waitForTauriPage(browser, () => null, 1_000), page);
  assert.equal(evaluations, 2);
});

test("Fail page readiness immediately when the application exits", async () => {
  const browser = { contexts: () => assert.fail("Do not inspect pages after process exit") };
  await assert.rejects(waitForTauriPage(browser, () => "process exited with code 7", 1_000),
    /portable Tauri page and IPC readiness: process exited with code 7/);
});

test("A missing Tauri bridge times out instead of accepting an unready page", async () => {
  const browser = { contexts: () => [{ pages: () => [{ evaluate: async () => false }] }] };
  await assert.rejects(waitForTauriPage(browser, () => null, 10),
    /timeout: portable Tauri page and IPC readiness/);
});
