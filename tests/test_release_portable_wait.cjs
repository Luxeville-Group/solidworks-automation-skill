/** @brief Verify portable waiter transient-connection retries and startup failure diagnostics without running the desktop app. */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { waitUntil } = require("../ai_team/release-portable-e2e.cjs");

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
