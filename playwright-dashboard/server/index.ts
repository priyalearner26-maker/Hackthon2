import express from "express";
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { Server } from "socket.io";
import { chromium, firefox, webkit, type BrowserType } from "playwright";

type TestStatus = "passed" | "failed" | "skipped" | "running" | "queued";
type TestCase = { id: string; storyKey: string; name: string; feature: string; priority: "P0" | "P1" | "P2"; tags: string[]; status: TestStatus; lastExecution: string; duration: number; error?: string; screenshot?: string };
type Story = { id: string; title: string; status: string; epic: string; tester: string; sprint: string; tests: TestCase[] };

const stories: Story[] = [
  { id: "BAIW-27", title: "Review Confluence page: Customer Verification", status: "To Do", epic: "Employee Workspace", tester: "Ravi Kumar", sprint: "Sprint 24", tests: [
    { id: "TC-2701", storyKey: "BAIW-27", name: "Open customer verification policy", feature: "Policy access", priority: "P0", tags: ["smoke", "chromium"], status: "passed", lastExecution: "Today, 09:18", duration: 842 },
    { id: "TC-2702", storyKey: "BAIW-27", name: "Reject incomplete verification", feature: "Validation", priority: "P0", tags: ["negative", "regression"], status: "failed", lastExecution: "Today, 09:18", duration: 1240, error: "Expected validation banner was not visible." },
    { id: "TC-2703", storyKey: "BAIW-27", name: "Persist approved identity checks", feature: "Audit trail", priority: "P1", tags: ["regression"], status: "passed", lastExecution: "Yesterday, 16:42", duration: 1675 },
    { id: "TC-2704", storyKey: "BAIW-27", name: "Restrict unassigned reviewer", feature: "Access control", priority: "P1", tags: ["security"], status: "skipped", lastExecution: "Yesterday, 16:42", duration: 0 },
  ] },
  { id: "BAIW-21", title: "Prevent disbursement for rejected loans", status: "In Progress", epic: "Loan Operations", tester: "Ananya Shah", sprint: "Sprint 24", tests: [
    { id: "TC-2101", storyKey: "BAIW-21", name: "Block rejected loan disbursement", feature: "Disbursement", priority: "P0", tags: ["critical", "api"], status: "passed", lastExecution: "Today, 08:52", duration: 1120 },
    { id: "TC-2102", storyKey: "BAIW-21", name: "Show rejection reason", feature: "User feedback", priority: "P1", tags: ["ui"], status: "passed", lastExecution: "Today, 08:52", duration: 930 },
    { id: "TC-2103", storyKey: "BAIW-21", name: "Audit blocked transaction", feature: "Audit trail", priority: "P1", tags: ["regression"], status: "failed", lastExecution: "Today, 08:52", duration: 1880, error: "Audit event did not contain the decision reason." },
  ] },
];

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, { cors: { origin: "*" } });
app.use(express.json());
let activeRun: { id: string; stop: boolean } | null = null;
for (const directory of ["artifacts/screenshots", "artifacts/videos", "artifacts/traces", "allure-results"]) fs.mkdirSync(path.resolve(directory), { recursive: true });

app.get("/api/stories", (_req, res) => res.json(stories.map(({ tests, ...story }) => ({ ...story, testCount: tests.length, lastResult: tests.some((test) => test.status === "failed") ? "failed" : "passed" }))));
app.get("/api/stories/:key/tests", (req, res) => {
  const story = stories.find((item) => item.id === req.params.key);
  if (!story) return res.status(404).json({ error: "Story not found" });
  return res.json({ story, tests: story.tests });
});
app.post("/api/execution/run", async (req, res) => {
  if (activeRun) return res.status(409).json({ error: "An execution is already running" });
  const story = stories.find((item) => item.id === req.body.storyKey);
  if (!story) return res.status(404).json({ error: "Select a valid story" });
  const selected = story.tests.filter((test) => !req.body.testIds?.length || req.body.testIds.includes(test.id));
  const run = { id: randomUUID(), stop: false };
  activeRun = run;
  res.status(202).json({ runId: run.id, total: selected.length });
  void executeRun(run, story, selected, req.body.browser ?? "chromium");
});
app.post("/api/execution/stop", (_req, res) => { if (activeRun) activeRun.stop = true; res.json({ status: "stopping" }); });
app.post("/api/execution/clear", (_req, res) => res.json({ status: "cleared" }));

async function executeRun(run: { id: string; stop: boolean }, story: Story, tests: TestCase[], browserName: string) {
  const browserType: BrowserType = browserName === "firefox" ? firefox : browserName === "webkit" ? webkit : chromium;
  const browser = await browserType.launch({ headless: true });
  const started = Date.now();
  io.emit("execution:started", { runId: run.id, storyKey: story.id, total: tests.length });
  try {
    for (const test of tests) {
      if (run.stop) { io.emit("execution:stopped", { runId: run.id }); break; }
      test.status = "running";
      io.emit("test:updated", { runId: run.id, test });
      io.emit("execution:log", { runId: run.id, message: `Running ${test.id} — ${test.name}` });
      const context = await browser.newContext({ recordVideo: { dir: path.resolve("artifacts/videos") } });
      await context.tracing.start({ screenshots: true, snapshots: true });
      const page = await context.newPage();
      page.on("console", (message) => io.emit("execution:log", { runId: run.id, message: `[browser:${message.type()}] ${message.text()}` }));
      const testStarted = Date.now();
      try {
        await page.goto("https://example.com", { waitUntil: "domcontentloaded", timeout: 15000 });
        await page.screenshot({ path: path.resolve(`artifacts/screenshots/${test.id}.png`), fullPage: true });
        test.screenshot = `/artifacts/screenshots/${test.id}.png`;
        test.status = "passed";
        test.error = undefined;
      } catch (error) {
        test.status = "failed";
        test.error = error instanceof Error ? error.message : "Playwright execution failed";
      } finally {
        test.duration = Date.now() - testStarted;
        test.lastExecution = "Just now";
        await context.tracing.stop({ path: path.resolve(`artifacts/traces/${test.id}.zip`) });
        await context.close();
        io.emit("test:updated", { runId: run.id, test });
      }
    }
  } finally {
    await browser.close();
    io.emit("execution:completed", { runId: run.id, duration: Date.now() - started, storyKey: story.id });
    activeRun = null;
  }
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
app.use(express.static(path.resolve(__dirname, "../dist")));
app.use("/artifacts", express.static(path.resolve("artifacts")));
app.get(/.*/, (_req, res) => res.sendFile(path.resolve(__dirname, "../dist/index.html")));
httpServer.listen(4175, () => console.log("Playwright dashboard API: http://127.0.0.1:4175"));