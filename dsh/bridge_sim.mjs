// Offline runner for the installed DSH Claude Code bridge. All state is supplied
// by the caller; this file does not load user hooks or start DSH.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";

const input = JSON.parse(readFileSync(0, "utf8"));
const { apply } = await import(pathToFileURL(input.bridge).href);
const handlers = new Map();
const agents = new Map();
const runs = [];
const warnings = [];
const ctx = {
  logger: { warn: (message) => warnings.push(String(message)), debug() {} },
  effect() {},
  on(point, handler) { handlers.set(point, handler); },
  get() { return undefined; },
  sessionProjections: { stateOf() { return { lastTurn: 1 }; } },
  workingDirectory: {
    get() { return input.workspace; },
    async ensure() { return input.workspace; },
  },
  shell: {
    resolve(request) { return request; },
    async execute(spec) {
      return { async result() {
        const started = performance.now();
        const child = spawnSync("bash", ["-c", spec.command], {
          cwd: spec.workdir ?? input.workspace,
          env: { ...process.env, ...spec.env },
          input: spec.stdin,
          encoding: "utf8",
          timeout: spec.timeoutMs,
        });
        runs.push({ durationMs: performance.now() - started, exitCode: child.status });
        return {
          exitCode: child.status ?? 1,
          stdout: { text: child.stdout ?? "" },
          stderr: { text: child.stderr ?? "" },
        };
      } };
    },
  },
};
apply(ctx, { configPath: input.config });

function agent(id) {
  if (!agents.has(id)) {
    const value = {
      session: { header: { id }, append() {} },
      injected: [],
      steered: [],
      inject(message) { this.injected.push(message); },
      steer(message) { this.steered.push(message); },
    };
    agents.set(id, value);
  }
  return agents.get(id);
}

const events = [];
for (const event of input.events) {
  const current = agent(event.id);
  const startRuns = runs.length;
  const startOutputs = event.kind === "start" ? current.injected.length : current.steered.length;
  const startTime = performance.now();
  if (event.kind === "start") {
    await handlers.get("agent/created")?.({ agent: current, source: event.source ?? "startup" });
  } else if (event.kind === "stop") {
    await handlers.get("agent/turn-stopping")?.({ agent: current, turn: event.turn ?? 1 });
  } else if (event.kind === "prompt") {
    await handlers.get("agent/pre-step")?.({
      agent: current, turn: event.turn ?? 1,
      messages: [{ content: [{ type: "text", text: event.text ?? "" }] }],
    }, async () => ({ kind: "enter", messages: [] }));
  } else {
    throw new Error(`unknown event kind: ${event.kind}`);
  }
  const output = event.kind === "start" ? current.injected : current.steered;
  events.push({
    kind: event.kind,
    id: event.id,
    turn: event.turn,
    contexts: output.slice(startOutputs).map((message) => message.content.map((block) => block.text).join("")),
    runCount: runs.length - startRuns,
    totalMs: performance.now() - startTime,
    hookMs: runs.slice(startRuns).reduce((sum, run) => sum + run.durationMs, 0),
  });
}
process.stdout.write(JSON.stringify({ events, warningCount: warnings.length }) + "\n");
