import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { io } from "socket.io-client";
import { Doughnut, Line } from "react-chartjs-2";
import { ArcElement, CategoryScale, Chart as ChartJS, Filler, Legend, LineElement, LinearScale, PointElement, Tooltip } from "chart.js";
import * as XLSX from "xlsx";
import { Button, Chip, LinearProgress } from "@mui/material";

ChartJS.register(ArcElement, CategoryScale, Filler, Legend, LineElement, LinearScale, PointElement, Tooltip);

type Status = "passed" | "failed" | "skipped" | "running" | "queued";
type TestCase = { id: string; storyKey: string; name: string; feature: string; priority: "P0" | "P1" | "P2"; tags: string[]; status: Status; lastExecution: string; duration: number; error?: string; screenshot?: string };
type Story = { id: string; title: string; status: string; epic: string; tester: string; sprint: string; testCount: number; lastResult: string; tests?: TestCase[] };

const api = axios.create({ baseURL: "/api" });
const socket = io();

function App() {
  const [stories, setStories] = useState<Story[]>([]);
  const [selectedStory, setSelectedStory] = useState<Story | null>(null);
  const [tests, setTests] = useState<TestCase[]>([]);
  const [selectedTests, setSelectedTests] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [epic, setEpic] = useState("All epics");
  const [sprint, setSprint] = useState("All sprints");
  const [browser, setBrowser] = useState("chromium");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<string[]>(["Execution console ready. Select a story to begin."]);
  const [error, setError] = useState("");
  const [trend] = useState([72, 78, 76, 84, 88, 91, 94]);

  useEffect(() => { void loadStories(); }, []);
  useEffect(() => {
    const update = (payload: { test: TestCase }) => { setTests((current) => { const next = current.map((test) => test.id === payload.test.id ? payload.test : test); const completed = next.filter((test) => ["passed", "failed", "skipped"].includes(test.status)).length; setProgress(next.length ? Math.round((completed / next.length) * 100) : 0); return next; }); };
    const log = (payload: { message: string }) => setLogs((current) => [...current.slice(-80), payload.message]);
    socket.on("test:updated", update);
    socket.on("execution:started", () => { setRunning(true); setProgress(0); setLogs(["Playwright execution started."]); });
    socket.on("execution:completed", () => { setRunning(false); setProgress(100); setLogs((current) => [...current, "Execution completed. Artifacts are available in the artifacts folder."]); });
    socket.on("execution:stopped", () => { setRunning(false); setLogs((current) => [...current, "Execution stopped by operator."]); });
    socket.on("execution:log", log);
    return () => { socket.off("test:updated", update); socket.off("execution:log", log); socket.off("execution:started"); socket.off("execution:completed"); socket.off("execution:stopped"); };
  }, []);

  async function loadStories() {
    try { const result = await api.get<Story[]>("/stories"); setStories(result.data); } catch { setError("Unable to load Jira stories from the execution service."); }
  }
  async function selectStory(story: Story) {
    setSelectedStory(story); setSelectedTests([]); setError("");
    try { const result = await api.get<{ story: Story; tests: TestCase[] }>(`/stories/${story.id}/tests`); setSelectedStory(result.data.story); setTests(result.data.tests); } catch { setError(`Unable to load mapped tests for ${story.id}.`); }
  }
  function toggleTest(id: string) { setSelectedTests((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  async function runTests(ids = selectedTests) {
    if (!selectedStory) return setError("Select a user story before running tests.");
    setError(""); setRunning(true); setProgress(0);
    try { await api.post("/execution/run", { storyKey: selectedStory.id, testIds: ids, browser }); } catch (requestError) { setRunning(false); setError(axios.isAxiosError(requestError) ? requestError.response?.data?.error ?? "Execution could not start." : "Execution could not start."); }
  }
  async function stopTests() { await api.post("/execution/stop"); }
  function clearResults() { setTests((current) => current.map((test) => ({ ...test, status: "queued", error: undefined, duration: 0, lastExecution: "Not run" }))); setProgress(0); setLogs(["Results cleared. Ready for a new run."]); }
  function exportResults() { const workbook = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(tests), "Test Results"); XLSX.writeFile(workbook, "nexa-test-results.xlsx"); }

  const filteredStories = stories.filter((story) => story.title.toLowerCase().includes(search.toLowerCase()) && (epic === "All epics" || story.epic === epic) && (sprint === "All sprints" || story.sprint === sprint));
  const counts = useMemo(() => ({ total: tests.length, passed: tests.filter((test) => test.status === "passed").length, failed: tests.filter((test) => test.status === "failed").length, skipped: tests.filter((test) => test.status === "skipped").length, running: tests.filter((test) => test.status === "running").length }), [tests]);
  const passPercentage = counts.total ? Math.round((counts.passed / counts.total) * 100) : 0;

  return <main className="execution-app">
    <header className="topbar"><div className="brand-mark">N</div><div><p className="eyebrow">NEXA ENGINEERING</p><h1>Playwright Test Command</h1></div><div className="topbar-meta"><span className="live-dot" /> Execution service online <span className="divider" /> Independent module</div></header>
    <section className="hero"><div><p className="eyebrow coral">QUALITY CONTROL / JIRA TRACEABILITY</p><h2>Turn stories into <em>evidence.</em></h2><p className="hero-copy">Select a user story, map its coverage, and run a browser matrix with live artifacts and traceable results.</p></div><div className="hero-stats"><strong>{stories.length.toString().padStart(2, "0")}</strong><span>Stories in execution queue</span></div></section>
    <div className="workspace-grid">
      <aside className="story-panel panel"><div className="panel-title"><div><p className="eyebrow">01 / SCOPE</p><h3>User stories</h3></div><span className="count">{filteredStories.length}</span></div><div className="search-box"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search stories..." /></div><div className="filters"><select value={epic} onChange={(event) => setEpic(event.target.value)}><option>All epics</option>{[...new Set(stories.map((story) => story.epic))].map((item) => <option key={item}>{item}</option>)}</select><select value={sprint} onChange={(event) => setSprint(event.target.value)}><option>All sprints</option>{[...new Set(stories.map((story) => story.sprint))].map((item) => <option key={item}>{item}</option>)}</select></div><div className="story-list">{filteredStories.map((story) => <button key={story.id} className={`story-card ${selectedStory?.id === story.id ? "active" : ""}`} onClick={() => void selectStory(story)}><div className="story-card-head"><strong>{story.id}</strong><span className={`status status-${story.status.toLowerCase().replace(" ", "-")}`}>{story.status}</span></div><h4>{story.title}</h4><div className="story-meta"><span>{story.epic}</span><span>{story.sprint}</span></div><div className="story-footer"><span>Tester: {story.tester}</span><span>{story.testCount} tests</span></div></button>)}</div></aside>
      <section className="main-column"><div className="panel selected-story">{selectedStory ? <><div className="selected-story-header"><div><p className="eyebrow coral">SELECTED STORY / {selectedStory.id}</p><h3>{selectedStory.title}</h3><p className="muted">{selectedStory.epic} <span className="dot-separator">•</span> {selectedStory.sprint} <span className="dot-separator">•</span> Assigned tester: {selectedStory.tester}</p></div><div className="browser-control"><label>Browser matrix</label><select value={browser} onChange={(event) => setBrowser(event.target.value)}><option value="chromium">Chromium</option><option value="firefox">Firefox</option><option value="webkit">WebKit</option></select></div></div><div className="story-pill-row"><Chip label={`${selectedStory.status}`} size="small" /><Chip label={`${tests.length} mapped cases`} size="small" variant="outlined" /><Chip label={`Last result: ${selectedStory.lastResult}`} size="small" variant="outlined" /></div></> : <div className="empty-selection"><p className="eyebrow coral">SELECT A STORY</p><h3>Your test scope starts here.</h3><p>Choose a story from the left to retrieve its linked Playwright coverage.</p></div>}</div>
        <div className="panel mapping-panel"><div className="panel-title"><div><p className="eyebrow">02 / COVERAGE</p><h3>Test case mapping</h3></div><div className="table-actions"><button className="text-button" onClick={() => setSelectedTests(tests.map((test) => test.id))} disabled={!tests.length}>Select all</button><button className="text-button" onClick={() => setSelectedTests(tests.filter((test) => test.status === "failed").map((test) => test.id))} disabled={!tests.length}>Failed only</button></div></div><div className="table-wrap"><table><thead><tr><th></th><th>Test case</th><th>Feature</th><th>Priority</th><th>Tags</th><th>Last execution</th><th>Status</th></tr></thead><tbody>{tests.map((test) => <tr key={test.id} className={selectedTests.includes(test.id) ? "row-selected" : ""}><td><input type="checkbox" checked={selectedTests.includes(test.id)} onChange={() => toggleTest(test.id)} /></td><td><strong>{test.id}</strong><span className="cell-subtitle">{test.name}</span></td><td>{test.feature}</td><td><span className={`priority priority-${test.priority.toLowerCase()}`}>{test.priority}</span></td><td><div className="tag-list">{test.tags.map((tag) => <span key={tag}>#{tag}</span>)}</div></td><td>{test.lastExecution}</td><td><span className={`result result-${test.status}`}>{test.status}</span></td></tr>)}</tbody></table>{!tests.length && <div className="empty-table">Select a story to load linked Playwright test cases.</div>}</div><div className="mapping-footer"><span>{selectedTests.length} selected</span><button className="outline-button" onClick={() => void runTests(selectedTests)} disabled={running || !selectedTests.length}>Execute selected</button><button className="outline-button" onClick={() => void runTests(tests.filter((test) => test.status === "failed").map((test) => test.id))} disabled={running || !tests.some((test) => test.status === "failed")}>Retry failed</button><button className="primary-button" onClick={() => void runTests([])} disabled={running || !tests.length}>Execute complete suite</button></div></div>
        <div className="panel execution-panel"><div className="panel-title"><div><p className="eyebrow">03 / RUNNER</p><h3>Execution controls</h3></div><div className="runner-status"><span className={`status-led ${running ? "active" : ""}`} />{running ? "Running" : "Ready"}</div></div><div className="execution-toolbar"><Button variant="contained" className="mui-run" onClick={() => void runTests()} disabled={running || !selectedTests.length}>Run tests <span>↗</span></Button><button className="outline-button danger" onClick={() => void stopTests()} disabled={!running}>Stop execution</button><button className="outline-button" onClick={clearResults}>Clear results</button><button className="outline-button" onClick={exportResults} disabled={!tests.length}>Export XLSX</button></div><LinearProgress variant="determinate" value={running ? Math.min(progress + counts.passed / Math.max(counts.total, 1) * 100, 99) : progress} className="progress-bar" /><div className="counter-row"><span><b>{counts.running}</b> running</span><span className="good"><b>{counts.passed}</b> passed</span><span className="bad"><b>{counts.failed}</b> failed</span><span><b>{counts.skipped}</b> skipped</span></div><div className="log-window">{logs.map((line, index) => <div key={`${line}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span>{line}</div>)}</div></div></section>
      <aside className="insights-column"><div className="panel summary-panel"><div className="panel-title"><div><p className="eyebrow">04 / SIGNAL</p><h3>Run summary</h3></div><span className="pass-ring">{passPercentage}%</span></div><div className="summary-grid"><Metric label="Total tests" value={counts.total} /><Metric label="Passed" value={counts.passed} tone="good" /><Metric label="Failed" value={counts.failed} tone="bad" /><Metric label="Skipped" value={counts.skipped} /></div><div className="chart-box"><Doughnut data={{ labels: ["Passed", "Failed", "Skipped"], datasets: [{ data: [counts.passed, counts.failed, counts.skipped], backgroundColor: ["#55d6a7", "#ff746d", "#c5cbd8"], borderWidth: 0 }] }} options={{ plugins: { legend: { position: "bottom", labels: { color: "#7b8496", boxWidth: 10, padding: 16 } } }, cutout: "72%" }} /></div></div><div className="panel trend-panel"><div className="panel-title"><div><p className="eyebrow">05 / MOMENTUM</p><h3>Execution trend</h3></div><span className="trend-up">+22%</span></div><div className="chart-box trend-chart"><Line data={{ labels: ["M-6", "M-5", "M-4", "M-3", "M-2", "M-1", "Now"], datasets: [{ data: trend, borderColor: "#ef8b62", backgroundColor: "rgba(239,139,98,.12)", fill: true, tension: .4, pointRadius: 3 }] }} options={{ plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: "#8d96a8" } }, y: { display: false } } }} /></div></div><div className="panel result-detail"><div className="panel-title"><div><p className="eyebrow">06 / EVIDENCE</p><h3>Selected result</h3></div></div>{tests.find((test) => test.status === "failed") ? <div className="failure-detail"><span className="result result-failed">Failed</span><strong>{tests.find((test) => test.status === "failed")?.name}</strong><p>{tests.find((test) => test.status === "failed")?.error}</p>{tests.find((test) => test.status === "failed")?.screenshot ? <a className="text-button" href={tests.find((test) => test.status === "failed")?.screenshot} target="_blank" rel="noreferrer">Open screenshot ↗</a> : <span className="muted">Screenshot will appear after a failed browser capture.</span>}</div> : <div className="empty-evidence">Run a suite to inspect screenshots, videos, traces, and console logs for each test.</div>}</div></aside>
    </div>{error && <div className="toast-error">{error}</div>}
  </main>;
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) { return <div className="metric"><span>{label}</span><strong className={tone}>{value.toString().padStart(2, "0")}</strong></div>; }

export default App;