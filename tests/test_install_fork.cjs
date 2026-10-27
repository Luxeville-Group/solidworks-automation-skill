const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../install.js"), "utf8");

function runInstaller(remote, failPull = false) {
  const calls = [];
  const removals = [];
  const home = path.join(path.parse(process.cwd()).root, "test-home");
  const skills = path.join(home, ".codex", "skills");
  const target = path.join(skills, "solidworks-automation");
  const mockFs = {
    existsSync: p => p === skills || p === target,
    mkdirSync: () => {},
    rmSync: p => removals.push(p),
  };
  const child = {
    execFileSync: (command, args) => {
      calls.push([command, args]);
      if (command === "git" && args[0] === "remote") return remote;
      if (command === "git" && args[0] === "pull" && failPull) throw new Error("local changes");
      return "";
    },
  };
  const requireMock = name => {
    if (name === "fs") return mockFs;
    if (name === "child_process") return child;
    if (name === "os") return { homedir: () => home };
    if (name === "path") return path;
    throw new Error("Unexpected module: " + name);
  };
  let exitCode;
  vm.runInNewContext(source, {
    require: requireMock,
    console: { log() {}, error() {} },
    process: { exit: code => { exitCode = code; } },
  });
  return { calls, removals, exitCode };
}

test("fork installation explicitly updates from origin with fast-forward only", () => {
  const result = runInstaller("https://github.com/Luxeville-Group/solidworks-automation-skill.git");
  assert.equal(result.exitCode, undefined);
  assert.deepEqual(Array.from(result.calls.find(([cmd, args]) => cmd === "git" && args[0] === "pull")[1]),
    ["pull", "--ff-only", "origin"]);
});

test("an upstream installation is retained and cannot silently replace the localized fork", () => {
  const result = runInstaller("https://github.com/wzyn20051216/solidworks-automation-skill.git");
  assert.equal(result.exitCode, 1);
  assert.equal(result.calls.some(([cmd, args]) => cmd === "git" && args[0] === "pull"), false);
  assert.equal(result.removals.length, 0);
});

test("a failed update retains local files without re-cloning", () => {
  const result = runInstaller("git@github.com:Luxeville-Group/solidworks-automation-skill.git", true);
  assert.equal(result.exitCode, 1);
  assert.equal(result.removals.length, 0);
  assert.equal(result.calls.some(([cmd, args]) => cmd === "git" && args[0] === "clone"), false);
});
