"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Bell,
  BookOpen,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  CheckCheck,
  Copy,
  FileText,
  FolderOpen,
  Mail,
  MessageSquareText,
  PencilLine,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { getDashboardSummary, getEmailMessages, sendEmail, sendMessage, uploadDocument } from "../lib/api";

type MessageRole = "assistant" | "user";
type AgentId = "email" | "meeting" | "jira" | "confluence" | "document" | "knowledge" | "assistant";
type TaskStatus = "Pending" | "In progress" | "Completed";

type Message = {
  id: number;
  role: MessageRole;
  text: string;
  time: string;
};

type JiraIssue = {
  key: string;
  summary: string;
  project: string;
  status: string;
  assignee: string;
  updated: string;
};

type EmailRow = {
  sender: string;
  senderEmail: string;
  subject: string;
  priority: string;
  summary: string;
  received: string;
  attachments: string;
};

type MeetingPreview = {
  subject: string;
  start: string;
  location: string;
};

type ConfluenceDetails = {
  title: string;
  pageId: string;
  source: string;
};

type ConfluenceResult = {
  title: string;
  pageId: string;
  preview: string;
};

const agents: Array<{
  id: AgentId;
  name: string;
  description: string;
  accent: string;
  icon: typeof Mail;
  count: number;
}> = [
  {
    id: "email",
    name: "MailMate",
    description: "Manage emails, get summaries, actions and draft replies",
    accent: "red",
    icon: Mail,
    count: 5,
  },
  {
    id: "meeting",
    name: "MeetMate",
    description: "Schedule meetings, create MOMs and track actions",
    accent: "purple",
    icon: CalendarDays,
    count: 0,
  },
  {
    id: "jira",
    name: "JiraPilot",
    description: "Turn requirements into Jira stories and track progress",
    accent: "blue",
    icon: BriefcaseBusiness,
    count: 0,
  },
  {
    id: "confluence",
    name: "Confluence Coach",
    description: "Search, summarize and create Confluence pages",
    accent: "cyan",
    icon: FolderOpen,
    count: 0,
  },
  {
    id: "document",
    name: "Document Analyzer",
    description: "Upload, analyze and extract information from documents",
    accent: "purple",
    icon: FileText,
    count: 0,
  },
  {
    id: "knowledge",
    name: "Knowledge Hub",
    description: "Find answers from bank policies and documents",
    accent: "blue",
    icon: BookOpen,
    count: 0,
  },
  {
    id: "assistant",
    name: "AskBank",
    description: "Get instant help on banking processes and general queries",
    accent: "dark",
    icon: Bot,
    count: 0,
  },
];

const recentConversations: Array<{ id: AgentId; label: string; time: string; icon: typeof Mail }> = [
  { id: "email", label: "Email: Q3 report review", time: "2 min ago", icon: Mail },
  { id: "meeting", label: "Meeting: Product roadmap", time: "1 hour ago", icon: CalendarDays },
  { id: "jira", label: "Jira: User stories for BRD", time: "3 hours ago", icon: BriefcaseBusiness },
  { id: "document", label: "Document: HR policy", time: "1 day ago", icon: FileText },
];

const navItems = [
  { id: "ai-agents", label: "Dashboard", icon: MessageSquareText },
  { id: "documents", label: "Document Analyzer", icon: FileText },
  { id: "knowledge", label: "Knowledge Hub", icon: BookOpen },
  { id: "jira", label: "Jira", icon: FolderOpen },
  { id: "confluence", label: "Confluence", icon: BookOpen },
];

const detailPanelsByAgent = {
  email: {
    title: "Email Details",
    detailItems: [{ label: "Status", value: "No email selected" }],
    summary: "Select an email from the live mailbox results to see its summary.",
    actionItems: ["Select an email to view its action items."],
    draftLines: ["Select an email to generate a reply draft."],
  },
  meeting: {
    title: "Meeting Details",
    detailItems: [
      { label: "Topic", value: "Product roadmap review" },
      { label: "Time", value: "Today, 2:30 PM" },
      { label: "Participants", value: "Product, Design, Engineering" },
      { label: "Notes", value: "Track launch dependencies and blockers" },
    ],
    summary:
      "The next roadmap review is scheduled for today and includes launch dependencies, staffing updates, and open blockers that need follow-through.",
    actionItems: [
      "Share the updated roadmap before the meeting (Owner: You)",
      "Capture blockers and assign owners (Owner: Team)",
    ],
    draftLines: [
      "Hi team,",
      "Please review the roadmap updates and share any blockers before the 2:30 PM meeting.",
      "Thanks,",
      "Sampath",
    ],
  },
  jira: {
    title: "Jira Details",
    detailItems: [
      { label: "Project", value: "Waiting for live Jira data" },
      { label: "Status", value: "Not loaded yet" },
      { label: "Recent issue", value: "-" },
      { label: "Updated", value: "-" },
    ],
    summary:
      "Live Jira issues will appear here once the workspace loads project activity from the configured Jira project.",
    actionItems: [
      "Load recent project activity to review active work items.",
      "Check the Jira issue list for the latest status, owner, and updated timestamp.",
    ],
    draftLines: [
      "Hi team,",
      "I’m waiting on the live Jira issue feed to confirm the current project status and open work.",
      "I’ll follow up once the latest items are loaded.",
      "Best,",
      "Sampath",
    ],
  },
  confluence: {
    title: "Confluence Details",
    detailItems: [
      { label: "Page", value: "No live page selected" },
      { label: "Page ID", value: "-" },
      { label: "Source", value: "Waiting for Confluence" },
      { label: "Status", value: "Not loaded" },
    ],
    summary: "Search Confluence to load a live page and its current content.",
              actionItems: ["Search Confluence pages to load live content and page details."],
    draftLines: ["A live Confluence page is required before preparing a response."],
  },
  document: {
    title: "Document Analyzer Details",
    detailItems: [
      { label: "File", value: "HR_policy_v2.pdf" },
      { label: "Owner", value: "HR" },
      { label: "Status", value: "Reviewed" },
      { label: "Key Section", value: "Leave policy" },
    ],
    summary:
      "The reviewed HR policy document has the updated leave eligibility and approval rules, including the new effective date for policy adoption.",
    actionItems: [
      "Share the revised policy with managers (Owner: HR)",
      "Update internal reminders for the new effective date (Owner: You)",
    ],
    draftLines: [
      "Hi managers,",
      "The revised HR policy is now available and includes the updated leave rules and effective date.",
      "Please review and share feedback by Friday.",
      "Best,",
      "Sampath",
    ],
  },
  knowledge: {
    title: "Knowledge Details",
    detailItems: [
      { label: "Source", value: "Approved knowledge base" },
      { label: "Match", value: "Policy search result" },
      { label: "Confidence", value: "High" },
      { label: "Updated", value: "This week" },
    ],
    summary:
      "The knowledge agent found a high-confidence policy match and summarized the approved guidance for quick reference.",
    actionItems: [
      "Attach the approved policy summary in the response (Owner: You)",
      "Verify that the latest revision is in the knowledge base (Owner: Ops)",
    ],
    draftLines: [
      "Hi team,",
      "I found an approved knowledge-base match with the latest policy language and summary.",
      "Please use the linked summary as the source of truth.",
      "Regards,",
      "Sampath",
    ],
  },
  assistant: {
    title: "Assistant Details",
    detailItems: [
      { label: "Mode", value: "General Q&A" },
      { label: "Capabilities", value: "Policy, procedures, and process guidance" },
      { label: "Context", value: "Nexa Bank workspace" },
      { label: "Status", value: "Ready" },
    ],
    summary:
      "The assistant is ready to answer general questions, help with process guidance, and summarize cross-team information from approved sources.",
    actionItems: [
      "Ask a follow-up question to narrow the request (Owner: You)",
      "Refine the query for a specialist agent if needed (Owner: Assistant)",
    ],
    draftLines: [
      "Hi team,",
      "I’m ready to help with general banking and process questions, and I can route you to specialist agents when needed.",
      "Let me know what you’d like to review next.",
      "Best,",
      "Sampath",
    ],
  },
} as const;

const initialTasks: Array<{
  id: number;
  title: string;
  section: "MailMate" | "JiraPilot" | "DocSense" | "Knowledge Hub" | "MeetMate" | "Workspace";
  owner: string;
  status: TaskStatus;
  updated: string;
  priority: "High" | "Medium" | "Low";
}> = [];

const initialMessagesByAgent: Record<string, Message[]> = {
  email: [
    { id: 1, role: "assistant", text: "Please read my latest unread emails and give me a summary with action items, priority and draft responses for important ones.", time: "10:24 AM" },
    { id: 2, role: "assistant", text: "I’ve read your unread emails. Here is the summary:", time: "10:24 AM" },
    { id: 3, role: "assistant", text: "You can click on any email to see full details, extract action items, or draft a response.", time: "10:24 AM" },
  ],
  meeting: [
    { id: 1, role: "assistant", text: "I can help you plan meetings, generate agendas, and track action items. What would you like to schedule?", time: "10:24 AM" },
  ],
  jira: [],
  confluence: [
    { id: 1, role: "assistant", text: "I can search your Confluence pages and summarize relevant policies, updates, and decisions quickly.", time: "10:24 AM" },
  ],
  document: [
    { id: 1, role: "assistant", text: "", time: "10:24 AM" },
  ],
  knowledge: [
    { id: 1, role: "assistant", text: "I can search approved knowledge sources and summarize the best matching policy or process guidance.", time: "10:24 AM" },
  ],
  assistant: [
    { id: 1, role: "assistant", text: "I’m ready to help with banking questions, process guidance, and cross-team summaries.", time: "10:24 AM" },
  ],
};

const documentProcessingStages = [
  "Reading document...",
  "Analyzing content...",
  "Extracting key details...",
  "Finalizing summary...",
];

function getTimestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function parseJiraIssues(answer: string): JiraIssue[] {
  const tableRows = answer
    .split(/\r?\n/)
    .filter((line) => line.trim().startsWith("|") && !line.includes("---"))
    .slice(1);
  if (tableRows.length > 0) {
    return tableRows.map((line) => line.split("|").slice(1, -1).map((cell) => cell.trim())).filter((cells) => cells.length >= 6).map((cells) => ({
      key: cells[0],
      summary: cells[1],
      project: cells[2],
      status: cells[3],
      assignee: cells[4],
      updated: cells[5],
    }));
  }

  const issuePattern = /([A-Z][A-Z0-9]+-\d+):\s*(.*?)\s*\|\s*Project:\s*([^|]+?)\s*\|\s*Status:\s*([^|]+?)\s*\|\s*Assignee:\s*([^|]+?)\s*\|\s*Updated:\s*(.*?)(?=\s+-\s+[A-Z][A-Z0-9]+-\d+:|$)/g;
  return Array.from(answer.matchAll(issuePattern), (match) => ({
    key: match[1].trim(),
    summary: match[2].trim(),
    project: match[3].trim(),
    status: match[4].trim(),
    assignee: match[5].trim(),
    updated: match[6].trim(),
  }));
}

function parseEmailRows(answer: string): EmailRow[] {
  const rows: EmailRow[] = [];
  let current: EmailRow | null = null;

  for (const line of answer.split(/\r?\n/)) {
    const match = line.match(/^[-*]\s+(.+?)\s+\|\s+from\s+(.+?)\s+\|\s+priority\s+(.+?)\s+\|\s+received\s+(.+)$/i);
    if (match) {
      const senderMatch = match[2].match(/^(.*?)\s*<([^>]+)>$/);
      current = {
        subject: match[1],
        sender: senderMatch?.[1]?.trim() ?? match[2],
        senderEmail: senderMatch?.[2]?.trim() ?? "",
        priority: match[3],
        received: match[4],
        summary: "",
        attachments: "",
      };
      rows.push(current);
      continue;
    }

    const summary = line.match(/^\s+Summary:\s*(.+)$/i);
    if (summary && current) current.summary = summary[1];
    const attachments = line.match(/^\s+Attachments:\s*(.+)$/i);
    if (attachments && current) current.attachments = attachments[1];
  }

  return rows;
}

function parseConfluenceDetails(answer: string): ConfluenceDetails | null {
  const pageLine = answer.split(/\r?\n/).find((line) => line.match(/^[-*]\s+.+\s+\(Page ID:\s*[^)]+\)/));
  if (!pageLine) return null;
  const match = pageLine.match(/^[-*]\s+(.+?)\s+\(Page ID:\s*([^)]+)\)/);
  if (!match) return null;
  return { title: match[1].trim(), pageId: match[2].trim(), source: "Live Confluence page" };
}

function parseConfluenceResults(answer: string): ConfluenceResult[] {
  const lines = answer.split(/\r?\n/);
  const results: ConfluenceResult[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^[-*]\s+(.+?)\s+\(Page ID:\s*([^)]+)\)/);
    if (!match) continue;
    const nextLine = lines[index + 1]?.trim() ?? "";
    results.push({
      title: match[1].trim(),
      pageId: match[2].trim(),
      preview: nextLine && !nextLine.startsWith("-") ? nextLine : "Live Confluence page",
    });
  }
  return results;
}

function parseConfluencePageContent(answer: string): string {
  const lines = answer.split(/\r?\n/);
  if (!lines.some((line) => line.trim() === "### Confluence Page")) return "";
  const pageLineIndex = lines.findIndex((line) => /^[-*]\s+.+\s+\(Page ID:\s*[^)]+\)/.test(line));
  return pageLineIndex >= 0 ? lines.slice(pageLineIndex + 1).join(" ").replace(/\s+/g, " ").trim() : "";
}

function buildConfluenceSummary(content: string): string {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return "The selected Confluence page has no readable body content.";
  const words = normalized.split(" ");
  if (words.length <= 220) return normalized;
  return `${words.slice(0, 220).join(" ")}...`;
}

function buildConfluenceActionItems(content: string): string[] {
  const items = content
    .split(/(?<=[.!?])\s+|\s{2,}/)
    .map((item) => item.trim().replace(/^[-*]\s*/, ""))
    .filter((item) => item.length > 12 && /\b(must|shall|should|required|acceptance|target date|next step|action|review|validate|work tracker)\b/i.test(item));
  return [...new Set(items)].slice(0, 3);
}

function buildJiraDetailSummary(issues: JiraIssue[]): string {
  if (!issues.length) {
    return "No live Jira issues were returned for this workspace.";
  }

  const recent = issues[0];
  const uniqueProjects = [...new Set(issues.map((issue) => issue.project).filter(Boolean))];
  const openCount = issues.filter((issue) => !/done|closed|resolved/i.test(issue.status)).length;
  const blockerCount = issues.filter((issue) => /blocker/i.test(issue.summary) || /blocker/i.test(issue.status)).length;
  const bugCount = issues.filter((issue) => /bug/i.test(issue.summary) || /bug/i.test(issue.status)).length;

  return `Live Jira data shows ${issues.length} result${issues.length === 1 ? "" : "s"} across ${uniqueProjects.length || 1} project${uniqueProjects.length === 1 ? "" : "s"}. Most recent: ${recent.key} — ${recent.summary} (${recent.status}) in ${recent.project}, updated ${recent.updated}. Open items: ${openCount}; blockers: ${blockerCount}; bugs: ${bugCount}.`;
}

function buildJiraActionItems(issues: JiraIssue[]): string[] {
  if (!issues.length) {
    return ["No live Jira action items were returned."];
  }

  return issues.slice(0, 3).map((issue) => {
    const label = /blocker/i.test(issue.summary) ? "Blocker" : /bug/i.test(issue.summary) ? "Bug" : "Issue";
    return `${label}: ${issue.key} — ${issue.summary} (${issue.status}; owner: ${issue.assignee}; updated: ${issue.updated})`;
  });
}

export function ChatWorkspace() {
  const [selectedNav, setSelectedNav] = useState("ai-agents");
  const [selectedAgent, setSelectedAgent] = useState<AgentId>("assistant");
  const [workspaceHome, setWorkspaceHome] = useState(true);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [emailRows, setEmailRows] = useState<EmailRow[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<EmailRow | null>(null);
  const [emailActionItems, setEmailActionItems] = useState<string[]>([]);
  const [emailDraftLines, setEmailDraftLines] = useState<string[]>([]);
  const [meetingPreview, setMeetingPreview] = useState<MeetingPreview[]>([]);
  const [confluencePreview, setConfluencePreview] = useState<string[]>([]);
  const [confluenceDetails, setConfluenceDetails] = useState<ConfluenceDetails | null>(null);
  const [confluencePageContent, setConfluencePageContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [taskFilter, setTaskFilter] = useState<"all" | "in-progress" | "pending" | "completed">("all");
  const [tasks, setTasks] = useState(initialTasks);
  const documentInputRef = useRef<HTMLInputElement>(null);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [detailPanelOpen, setDetailPanelOpen] = useState(true);
  const [statusMessage, setStatusMessage] = useState("");
  const [documentSummary, setDocumentSummary] = useState("");
  const [jiraIssues, setJiraIssues] = useState<JiraIssue[]>([]);
  const [documentProcessing, setDocumentProcessing] = useState(false);
  const [documentProcessingStage, setDocumentProcessingStage] = useState(0);
  const [dashboardMetrics, setDashboardMetrics] = useState({
    connected_integrations: 0,
    knowledge_documents: 0,
    integration_status: {} as Record<string, boolean>,
  });
  const dashboardLoadStarted = useRef(false);
  const mailboxLoad = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (dashboardLoadStarted.current) return;
    dashboardLoadStarted.current = true;

    void getDashboardSummary().then((summary) => {
      setDashboardMetrics({
        connected_integrations: summary.connected_integrations,
        knowledge_documents: summary.knowledge_documents,
        integration_status: summary.integration_status,
      });
    }).catch(() => setStatusMessage("Dashboard metrics are temporarily unavailable."));
    void loadMailboxPreview();
    void loadDashboardAgentData();
  }, []);

  useEffect(() => {
    if (!documentProcessing) return;

    const stageTimer = window.setInterval(() => {
      setDocumentProcessingStage((current) => Math.min(current + 1, documentProcessingStages.length - 1));
    }, 1200);

    return () => window.clearInterval(stageTimer);
  }, [documentProcessing]);

  const activeAgent = agents.find((agent) => agent.id === selectedAgent) ?? agents[0];
  const baseDetail = detailPanelsByAgent[selectedAgent] ?? detailPanelsByAgent.email;
  const hasSelectedConfluencePage = Boolean(confluenceDetails || confluencePageContent.trim());
  const activeDetail = selectedAgent === "email"
    ? selectedEmail
      ? {
          ...baseDetail,
          detailItems: [
            { label: "From", value: selectedEmail.sender },
            { label: "Subject", value: selectedEmail.subject },
            { label: "Received", value: selectedEmail.received },
            { label: "Priority", value: selectedEmail.priority },
            { label: "Attachments", value: selectedEmail.attachments || "None" },
          ],
          summary: selectedEmail.summary || "No message preview was returned.",
          actionItems: emailActionItems.length ? emailActionItems : ["Action items are available in the chat response."],
          draftLines: emailDraftLines.length ? emailDraftLines : ["Use Draft Responses to generate a reply."],
        }
      : {
          ...baseDetail,
          detailItems: [
            { label: "From", value: "No email selected" },
            { label: "Subject", value: "Select an email from the results" },
            { label: "Received", value: "-" },
            { label: "Priority", value: "-" },
            { label: "Attachments", value: "-" },
          ],
          summary: emailDraftLines.length
            ? "A new email draft is ready for review and editing."
            : "Search or load your mailbox to see actual email information here.",
          actionItems: ["Select an email to view its action items."],
          draftLines: emailDraftLines.length ? emailDraftLines : ["Select an email to generate a reply draft."],
        }
    : selectedAgent === "jira" && jiraIssues.length > 0
      ? {
          ...baseDetail,
          detailItems: [
            { label: "Issues", value: `${jiraIssues.length} loaded` },
            { label: "Project", value: [...new Set(jiraIssues.map((issue) => issue.project))].join(", ") || "N/A" },
            { label: "Statuses", value: [...new Set(jiraIssues.map((issue) => issue.status))].join(", ") || "N/A" },
            { label: "Assignees", value: [...new Set(jiraIssues.map((issue) => issue.assignee))].join(", ") || "N/A" },
          ],
          summary: buildJiraDetailSummary(jiraIssues),
          actionItems: buildJiraActionItems(jiraIssues),
          draftLines: jiraIssues.slice(0, 3).map((issue) => `Follow up on ${issue.key}: ${issue.summary} (${issue.status})`),
        }
      : selectedAgent === "confluence" && confluenceDetails
        ? {
            ...baseDetail,
            detailItems: [
              { label: "Page", value: confluenceDetails.title },
              { label: "Page ID", value: confluenceDetails.pageId },
              { label: "Source", value: confluenceDetails.source },
              { label: "Status", value: "Retrieved" },
            ],
            summary: buildConfluenceSummary(confluencePageContent),
            actionItems: buildConfluenceActionItems(confluencePageContent).length
              ? buildConfluenceActionItems(confluencePageContent)
              : ["No action items were identified in this page."],
            draftLines: [
              `Follow up on “${confluenceDetails.title}”.`,
              buildConfluenceSummary(confluencePageContent),
            ],
          }
        : selectedAgent === "confluence"
          ? {
              ...baseDetail,
              summary: "No live Confluence page is loaded. Search recent pages and select a result to view its details.",
              actionItems: ["Search Confluence pages for a topic or recent workspace update.", "Open a result to retrieve the complete live page content."],
              draftLines: ["Load a live Confluence page before preparing a response."],
            }
        : baseDetail;

  const filteredAgents = agents;

  const visibleAgents = selectedNav === "documents"
    ? filteredAgents.filter((agent) => agent.id === "document")
    : workspaceHome
      ? filteredAgents.filter((agent) => agent.id !== "jira" && agent.id !== "confluence")
      : filteredAgents.filter((agent) => agent.id === selectedAgent);

  const filteredTasks = useMemo(() => {
    if (taskFilter === "all") return tasks;

    if (taskFilter === "in-progress") {
      return tasks.filter((task) => task.status === "In progress");
    }

    if (taskFilter === "pending") {
      return tasks.filter((task) => task.status === "Pending");
    }

    return tasks.filter((task) => task.status === "Completed");
  }, [taskFilter, tasks]);

  async function loadMailboxPreview(showInChat = false) {
    if (mailboxLoad.current) {
      await mailboxLoad.current;
      return;
    }

    mailboxLoad.current = (async () => {
      try {
        const result = await getEmailMessages(true);
        const rows: EmailRow[] = result.messages.map((email) => ({
          sender: email.sender,
          senderEmail: email.sender_email,
          subject: email.subject,
          priority: email.priority,
          summary: email.body.slice(0, 240),
          received: email.received_at || "recently",
          attachments: email.attachment_names.join(", "),
        }));
        setEmailRows(rows);
        setSelectedEmail((current) => current ?? rows[0] ?? null);
        if (showInChat) {
          setMessages((current) => [
            ...current,
            { id: Date.now(), role: "assistant", text: `Loaded ${rows.length} unread email${rows.length === 1 ? "" : "s"}. Select a message below for details.`, time: getTimestamp() },
          ]);
        }
      } catch {
        if (showInChat) {
          setMessages((current) => [
            ...current,
            { id: Date.now(), role: "assistant", text: "MailMate could not load the mailbox. Check the Outlook profile or Microsoft Graph sign-in.", time: getTimestamp() },
          ]);
        }
      } finally {
        mailboxLoad.current = null;
      }
    })();

    try {
      await mailboxLoad.current;
    } catch {
      // The mailbox loader already converts failures into user-facing state.
    }
  }

  async function loadDashboardAgentData() {
    const [meetingResult, jiraResult, confluenceResult] = await Promise.allSettled([
      sendMessage("dashboard-session", "Show upcoming calendar meetings."),
      sendMessage("dashboard-session", "Show my recently updated Jira issues"),
      sendMessage("dashboard-session", "Search Confluence pages for recent workspace updates", "confluence"),
    ]);

    if (meetingResult.status === "fulfilled") {
      const events = meetingResult.value.answer.split(/\r?\n/).flatMap((line) => {
        const match = line.match(/^[-*]\s+(.+?)\s+to\s+(.+?)\s+\|\s+(.+?)(?:\s+\|\s+(.*))?$/);
        return match ? [{ start: `${match[1]} to ${match[2]}`, subject: match[3], location: match[4] || "" }] : [];
      });
      setMeetingPreview(events);
    }

    if (jiraResult.status === "fulfilled") {
      setJiraIssues(parseJiraIssues(jiraResult.value.answer));
    }

    if (confluenceResult.status === "fulfilled") {
      const pages = confluenceResult.value.answer
        .split(/\r?\n/)
        .filter((line) => line.startsWith("- "))
        .map((line) => line.replace(/^[-*]\s+/, ""));
      setConfluencePreview(pages);
    }
  }

  async function submitMessage(trimmed: string) {
    if (!trimmed || isLoading) return;

    const userMessage: Message = {
      id: Date.now(),
      role: "user",
      text: trimmed,
      time: getTimestamp(),
    };

    setMessages((current) => [...current, userMessage]);
    setMessage("");
    setIsLoading(true);

    try {
      const requestMessage = selectedAgent === "email"
        ? `Email request: ${trimmed}`
        : selectedAgent === "confluence" && confluenceDetails
          ? `Confluence page ${confluenceDetails.pageId}: ${trimmed}`
          : trimmed;
      const result = await sendMessage("employee-session", requestMessage, selectedAgent);
      let displayedAnswer = result.answer;
      if (result.route === "email" || selectedAgent === "email") {
        const parsedRows = parseEmailRows(result.answer);
        if (parsedRows.length) {
          setEmailRows(parsedRows);
          setSelectedEmail(parsedRows[0]);
          displayedAnswer = `Found ${parsedRows.length} email${parsedRows.length === 1 ? "" : "s"}. Select a message below to view details.`;
        }
        if (trimmed.toLowerCase().includes("action item")) {
          const actionStart = result.answer.indexOf("Action items:");
          const actionEnd = result.answer.indexOf("Draft reply for", actionStart);
          const actionText = actionStart >= 0
            ? result.answer.slice(actionStart + "Action items:".length, actionEnd >= 0 ? actionEnd : undefined)
            : result.answer;
          const items = actionText
            .split(/\r?\n/)
            .filter((line) => line.trim().startsWith("- "))
            .map((line) => line.replace(/^\s*-\s*/, "").replace(/^[^:]+:\s*/, ""));
          setEmailActionItems(items);
        }
        if (trimmed.toLowerCase().includes("draft") || trimmed.toLowerCase().includes("reply")) {
          const draftHeading = result.answer.search(/(?:Draft reply for|New email draft:)/i);
          const draftStart = draftHeading >= 0 ? result.answer.indexOf("\n\n", draftHeading) : result.answer.indexOf("\n\n");
          const draft = draftStart >= 0 ? result.answer.slice(draftStart + 2) : result.answer;
          setEmailDraftLines(draft.split(/\r?\n/).filter(Boolean));
          displayedAnswer = result.answer.toLowerCase().includes("new email draft")
            ? "New email draft prepared. Review and edit it before sending."
            : "Draft response prepared. Review it in the email details panel.";
        }
      }
      if (selectedAgent === "jira") {
        setJiraIssues(parseJiraIssues(result.answer));
      }
      if (selectedAgent === "confluence") {
        const pageDetails = parseConfluenceDetails(result.answer);
        const pageContent = parseConfluencePageContent(result.answer);
        setConfluenceDetails(pageContent ? pageDetails : null);
        setConfluencePageContent(pageContent);
        setConfluencePreview(result.answer.split(/\r?\n/).filter((line) => line.startsWith("- ")).map((line) => line.replace(/^[-*]\s+/, "")));
        if (pageContent && pageDetails) {
          displayedAnswer = `Selected Confluence page: ${pageDetails.title} (Page ID: ${pageDetails.pageId}). The full page content is available in the details panel.`;
        }
      }
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: displayedAnswer,
          time: getTimestamp(),
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 2,
          role: "assistant",
          text: "The assistant is unavailable right now. Please check that the FastAPI service is running.",
          time: getTimestamp(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage(message.trim());
  }

  function handleMessageKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage(message.trim());
    }
  }

  async function handleDocumentUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || isLoading) return;

    setIsLoading(true);
    setDocumentProcessing(true);
    setDocumentProcessingStage(0);
    try {
      const result = await uploadDocument(file);
      const { analysis } = result;
      const details = [
        analysis.summary,
        analysis.action_items.length ? `Action items:\n${analysis.action_items.map((item) => `- ${item}`).join("\n")}` : "No action items detected.",
        analysis.keywords.length ? `Keywords: ${analysis.keywords.join(", ")}` : "",
      ].filter(Boolean).join("\n\n");
      setDocumentSummary(details);
      setMessages((current) => [...current, { id: Date.now(), role: "assistant", text: analysis.summary, time: getTimestamp() }]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: Date.now(), role: "assistant", text: error instanceof Error ? error.message : "Document analysis failed.", time: getTimestamp() },
      ]);
    } finally {
      setDocumentProcessing(false);
      setIsLoading(false);
    }
  }

  async function handleSendDraft() {
    if (!selectedEmail) {
      setStatusMessage("Select an email before sending a draft.");
      return;
    }

    const recipient = selectedEmail.senderEmail || selectedEmail.sender.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/)?.[0];
    if (!recipient) {
      const enteredRecipient = window.prompt("Recipient email address:");
      if (!enteredRecipient?.trim()) {
        setStatusMessage("A recipient email address is required before sending.");
        return;
      }
      if (!/^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$/.test(enteredRecipient.trim())) {
        setStatusMessage("Enter a valid recipient email address.");
        return;
      }
      return handleSendDraftTo(enteredRecipient.trim(), selectedEmail.subject, activeDetail.draftLines.join("\n"));
    }

    return handleSendDraftTo(recipient, selectedEmail.subject, activeDetail.draftLines.join("\n"));
  }

  async function handleSendDraftTo(recipient: string, subject: string, body: string) {

    try {
      const result = await sendEmail(
        recipient,
        `Re: ${subject}`,
        body,
      );
      setStatusMessage(`Email sent via ${result.provider} to ${recipient}.`);
      setMessages((current) => [
        ...current,
        { id: Date.now(), role: "assistant", text: `Email sent via ${result.provider} to ${recipient}.`, time: getTimestamp() },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Outlook could not send the draft.";
      setStatusMessage(message);
      setMessages((current) => [
        ...current,
        {
          id: Date.now(),
          role: "assistant",
          text: message,
          time: getTimestamp(),
        },
      ]);
    }
  }

  async function loadJiraOverview() {
    setIsLoading(true);
    setStatusMessage("Loading live Jira activity...");

    try {
      const result = await sendMessage("employee-session", "Show my recently updated Jira issues", "jira");
      setJiraIssues(parseJiraIssues(result.answer));
      setMessages((current) => [
        ...current,
        { id: Date.now(), role: "assistant", text: result.answer, time: getTimestamp() },
      ]);
      setStatusMessage("Live Jira activity loaded.");
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: Date.now(),
          role: "assistant",
          text: "Jira activity could not be loaded. Please check that the FastAPI service is running.",
          time: getTimestamp(),
        },
      ]);
      setStatusMessage("Jira activity could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleAgentClick(agentId: AgentId) {
    setSelectedAgent(agentId);
    setWorkspaceHome(false);
    setDetailPanelOpen(true);
    setMessages(agentId === "email" || agentId === "jira" ? [] : [...(initialMessagesByAgent[agentId] ?? [])]);
    setMessage("");
    setJiraIssues([]);
    setConfluenceDetails(null);
    setConfluencePageContent("");
    setConfluencePreview([]);
    setEmailRows([]);
    setSelectedEmail(null);
    setEmailActionItems([]);
    setEmailDraftLines([]);
    setStatusMessage(`${agents.find((agent) => agent.id === agentId)?.name ?? "Workspace"} is ready.`);
    if (agentId === "jira") {
      void loadJiraOverview();
    }
  }

  function handleSidebarToolClick(agentId: AgentId) {
    setSelectedNav("ai-agents");
    handleAgentClick(agentId);
  }

  function handleViewUnreadEmails() {
    handleSidebarToolClick("email");
    void loadMailboxPreview(true);
  }

  function handleEmailDraft() {
    if (!selectedEmail) {
      setStatusMessage("Select an email before drafting a response.");
      return;
    }

    const subject = selectedEmail.subject || "the selected email";
    void submitMessage(`Draft a reply for ${subject}`);
  }

  function handleEmailSelection(email: EmailRow) {
    setSelectedEmail(email);
    setEmailActionItems([]);
    setEmailDraftLines([]);
    setStatusMessage(`Preparing a professional reply for ${email.subject}...`);
    void submitMessage(`Draft a reply for ${email.subject}`);
  }

  function handleNewEmailDraft() {
    const instruction = window.prompt("What should the new email say?");
    if (!instruction?.trim() || isLoading) return;
    void submitMessage(`Draft a new email: ${instruction.trim()}`);
  }

  function handleScheduleMeeting() {
    if (isLoading) return;
    const subject = window.prompt("Meeting subject:", "Weekly sync");
    if (!subject?.trim()) return;
    const start = window.prompt("Start time (YYYY-MM-DD HH:MM):", "2026-09-17 14:00");
    if (!start?.trim()) return;
    const duration = window.prompt("Duration in minutes:", "45");
    if (!duration?.trim() || !/^\d+$/.test(duration.trim())) {
      setStatusMessage("Enter a duration in minutes before scheduling.");
      return;
    }
    void submitMessage(`Schedule meeting: ${subject.trim()} | ${start.trim()} | ${duration.trim()}`);
  }

  async function handleEmailSearch() {
    if (isLoading) return;

    setMessages((current) => [
      ...current,
      { id: Date.now(), role: "user", text: "Show all unread mail", time: getTimestamp() },
    ]);
    setIsLoading(true);

    try {
      const result = await getEmailMessages(true);
      const rows: EmailRow[] = result.messages.map((email) => ({
        sender: email.sender,
        senderEmail: email.sender_email,
        subject: email.subject,
        priority: email.priority,
        summary: email.body.slice(0, 240),
        received: email.received_at || "recently",
        attachments: email.attachment_names.join(", "),
      }));
      setEmailRows(rows);
      setSelectedEmail(rows[0] ?? null);
      setEmailActionItems([]);
      setEmailDraftLines([]);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: rows.length
            ? `Found ${rows.length} unread email${rows.length === 1 ? "" : "s"}. Select a message below to view details.`
            : "No unread emails matched that search.",
          time: getTimestamp(),
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: error instanceof Error ? error.message : "Unable to search unread mail.",
          time: getTimestamp(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function startNewChat() {
    setMessages([]);
    setMessage("");
    setDocumentSummary("");
    setJiraIssues([]);
    setConfluenceDetails(null);
    setConfluencePageContent("");
    setEmailRows([]);
    setSelectedEmail(null);
    setEmailActionItems([]);
    setEmailDraftLines([]);
    setStatusMessage(`New ${activeAgent.name} chat started.`);
  }

  function addWidget() {
    setTasks((current) => [
      ...current,
      { id: Date.now(), title: "Review new workspace widget", section: "Workspace", owner: "Sampath", status: "Pending", updated: "just now", priority: "Low" },
    ]);
    setStatusMessage("A new workspace task widget was added.");
  }

  async function copyDraft() {
    const draft = activeDetail.draftLines.join("\n");
    try {
      if (!navigator.clipboard) throw new Error("Clipboard is unavailable");
      await navigator.clipboard.writeText(draft);
      setStatusMessage("Draft copied to clipboard.");
    } catch {
      setStatusMessage("The draft could not be copied. Use Edit to place it in the composer.");
    }
  }

  function editDraft() {
    if (!emailDraftLines.length && selectedAgent === "email") {
      if (selectedEmail) {
        handleEmailDraft();
      } else {
        handleNewEmailDraft();
      }
      return;
    }
    setMessage(activeDetail.draftLines.join("\n"));
    setStatusMessage("Draft loaded into the composer for editing.");
  }

  function handleUtilityAction() {
    if (selectedAgent === "meeting") {
      void submitMessage("Open Microsoft Teams");
      return;
    }
    if (selectedAgent === "email") {
      if (!emailDraftLines.length) {
        if (selectedEmail) {
          handleEmailDraft();
        } else {
          handleNewEmailDraft();
        }
        return;
      }
      if (selectedEmail) {
        void handleSendDraft();
      } else {
        editDraft();
      }
      return;
    }
    if (selectedAgent === "confluence") {
      if (!confluenceDetails) {
        setStatusMessage("Select a Confluence page before updating it.");
        return;
      }
      const content = window.prompt("Replacement content for the selected Confluence page:", confluencePageContent);
      if (!content?.trim()) return;
      void submitMessage(`Update Confluence page ${confluenceDetails.pageId}: ${content.trim()}`);
      return;
    }
    void submitMessage(`Send the current ${activeAgent.name} response.`);
  }

  function selectConfluencePage(page: ConfluenceResult) {
    setConfluenceDetails({ title: page.title, pageId: page.pageId, source: "Live Confluence page" });
    setConfluencePageContent(page.preview);
    setStatusMessage(`Loading ${page.title}...`);
    void submitMessage(`Open Confluence page /pages/${page.pageId}`);
  }

  function startConfluenceCreate() {
    const title = window.prompt("Confluence page title:");
    if (!title?.trim()) return;
    const body = window.prompt("Confluence page content:");
    if (!body?.trim()) return;
    void submitMessage(`Create a Confluence page: ${title.trim()} | ${body.trim()}`);
  }

  function startConfluenceUpdate() {
    const pageId = window.prompt("Confluence page ID:");
    if (!pageId?.trim()) return;
    const body = window.prompt("Replacement page content:");
    if (!body?.trim()) return;
    void submitMessage(`Update Confluence page ${pageId.trim()}: ${body.trim()}`);
  }

  async function createJiraStoryFromConfluence() {
    if (!hasSelectedConfluencePage) {
      setStatusMessage("Select a Confluence page before creating a Jira story.");
      return;
    }
    const title = confluenceDetails?.title || "Selected Confluence page";
    const summary = `Review Confluence page: ${title}`.slice(0, 180);
    const context = confluencePageContent.replace(/\s+/g, " ").trim().slice(0, 5000);
    const request = context
      ? `Create a story in Jira: ${summary} | Context: ${context}`
      : `Create a story in Jira: ${summary}`;
    setIsLoading(true);
    try {
      const result = await sendMessage("confluence-jira-session", request, "jira");
      setMessages((current) => [
        ...current,
        { id: Date.now(), role: "assistant", text: result.answer, time: getTimestamp() },
      ]);
      setStatusMessage(result.answer);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to create the Jira story.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleNavClick(navId: string) {
    if (navId === "home") {
      setSelectedNav("ai-agents");
      handleAgentClick("assistant");
      return;
    }

    if (navId === "ai-agents") {
      setSelectedNav("ai-agents");
      setWorkspaceHome(true);
      setStatusMessage("Choose a workspace tool to get started.");
      return;
    }

    if (navId === "dashboard") {
      setSelectedNav("dashboard");
      return;
    }

    if (navId === "documents") {
      setSelectedNav("documents");
      handleAgentClick("document");
      return;
    }

    if (navId === "knowledge") {
      setSelectedNav("knowledge");
      handleAgentClick("knowledge");
      return;
    }

    if (navId === "jira") {
      setSelectedNav("ai-agents");
      handleAgentClick("jira");
      return;
    }

    if (navId === "confluence") {
      setSelectedNav("ai-agents");
      handleAgentClick("confluence");
      return;
    }

    if (navId === "calendar") {
      setSelectedNav("ai-agents");
      handleAgentClick("meeting");
      return;
    }

    setSelectedNav(navId);
  }

  return (
    <main className="workspace-shell">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand-mark">N</div>
          <div className="brand-copy">
            <p className="sidebar-label">Nexa Bank</p>
            <h2>Employee Workspace</h2>
          </div>
        </div>

        <nav className="nav-list" aria-label="Sidebar navigation">
          {navItems.filter(({ id }) => id === "ai-agents").map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item${selectedNav === id ? " active" : ""}`}
              type="button"
              onClick={() => handleNavClick(id)}
            >
              <Icon size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-tools">
          <div className="sidebar-footer-title">Workspace Tools</div>
          <div className="nav-list">
            {navItems.filter(({ id }) => id !== "ai-agents").map(({ id, label, icon: Icon }) => (
              <button
                key={`workspace-${id}`}
                type="button"
                className={`nav-item${selectedNav === id ? " active" : ""}`}
                onClick={() => handleNavClick(id)}
              >
                <Icon size={17} />
                <span>{label}</span>
              </button>
            ))}
            {agents.filter(({ id }) => !["knowledge", "document", "jira", "confluence"].includes(id)).map(({ id, name, icon: Icon }) => (
              <button
                key={`tool-${id}`}
                type="button"
                className={`nav-item${selectedAgent === id && selectedNav === "ai-agents" && !workspaceHome ? " active" : ""}`}
                onClick={() => handleSidebarToolClick(id)}
              >
                <Icon size={17} />
                <span>{name}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="sidebar-footer">
          <div className="sidebar-footer-title">Recent Conversations</div>
          <div className="conversation-list">
            {recentConversations.map(({ id, label, time, icon: Icon }) => (
              <button key={id} type="button" className={`conversation-item${selectedAgent === id ? " selected" : ""}`} onClick={() => handleAgentClick(id)}>
                <span className="conversation-icon">
                  <Icon size={14} />
                </span>
                <span className="conversation-copy">
                  <span className="conversation-label">{label}</span>
                  <span className="conversation-time">{time}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <section className="workspace-content">
        <header className="topbar">
          <div className="topbar-actions">
            <button type="button" className="icon-button" aria-label="Notifications" onClick={() => setNotificationsOpen((current) => !current)}>
              <Bell size={18} />
            </button>
            {notificationsOpen && <div className="notification-popover">No new notifications.</div>}
          </div>
        </header>
        {statusMessage && <div className="status-message" role="status">{statusMessage}</div>}

        {selectedNav === "dashboard" ? (
          <section className="dashboard-panel">
            <div className="dashboard-header">
              <div>
                <p className="dashboard-label">Overview</p>
                <h3>Dashboard</h3>
              </div>
              <button type="button" className="primary-button" onClick={addWidget}>
                <Plus size={16} />
                Add widget
              </button>
            </div>

            <div className="dashboard-grid">
              <div className="dashboard-card">
                <span>Jira connection</span>
                <strong>{dashboardMetrics.integration_status?.Jira ? "Connected" : "Not connected"}</strong>
                <small>Used for project and issue activity</small>
              </div>
              <div className="dashboard-card">
                <span>Knowledge base</span>
                <strong>{dashboardMetrics.knowledge_documents}</strong>
                <small>Approved documents indexed</small>
              </div>
            </div>

            <section className="dashboard-observability" aria-label="AI observability">
              <div>
                <p className="dashboard-label">AI quality</p>
                <h4>Observability</h4>
                <p>LangSmith tracking, Ragas evaluation, and guardrail validation.</p>
              </div>
              <div className="dashboard-observability-statuses">
                <span><i className="status-dot active" />LangSmith</span>
                <span><i className="status-dot neutral" />Ragas</span>
                <span><i className="status-dot active" />Guardrails</span>
              </div>
              <a className="secondary-button" href="/observability">Open observability</a>
            </section>

            <div className="dashboard-table-card">
              <div className="dashboard-table-header">
                <span>My Tasks</span>
                <div className="task-filter-group">
                  <button type="button" className={`filter-button${taskFilter === "all" ? " active" : ""}`} onClick={() => setTaskFilter("all")}>All</button>
                  <button type="button" className={`filter-button${taskFilter === "pending" ? " active" : ""}`} onClick={() => setTaskFilter("pending")}>Pending</button>
                  <button type="button" className={`filter-button${taskFilter === "in-progress" ? " active" : ""}`} onClick={() => setTaskFilter("in-progress")}>In progress</button>
                  <button type="button" className={`filter-button${taskFilter === "completed" ? " active" : ""}`} onClick={() => setTaskFilter("completed")}>Completed</button>
                </div>
              </div>

              <div className="dashboard-table">
                <div className="dashboard-row dashboard-row-head">
                  <span>Task</span>
                  <span>Status</span>
                  <span>Updated</span>
                  <span>Action</span>
                </div>

                {filteredTasks.map((task) => (
                  <div key={task.id} className="dashboard-row">
                    <span>{task.title}</span>
                    <span className={`status-pill ${task.status === "Completed" ? "success" : task.status === "Pending" ? "neutral" : "warning"}`}>
                      {task.status}
                    </span>
                    <span>{task.updated}</span>
                    <span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : (
          <div className={`main-grid${workspaceHome ? " tools-only-grid" : " focused-tool-grid"}`}>
            {workspaceHome && <section className="agent-list-panel">
              <div className="workspace-overview">
                <div className="dashboard-header">
                  <div>
                    <p className="dashboard-label">Overview</p>
                    <h3>Dashboard</h3>
                  </div>
                  <span className="workspace-status">Workspace ready</span>
                </div>
                <div className="dashboard-detail-grid">
                  <div className="dashboard-detail-card open-tasks-card">
                    <div className="dashboard-detail-heading"><CheckCheck size={16} /><span>Open tasks</span><strong>{tasks.filter((task) => task.status !== "Completed").length}</strong></div>
                    <p>Tasks that still need attention</p>
                    {tasks.filter((task) => task.status !== "Completed").map((task) => (
                      <div key={task.id} className="dashboard-task-item">
                        <div>
                          <strong>{task.title}</strong>
                          <span className="task-section-pill">{task.section}</span>
                          <div className="task-meta-row">
                            <span className={`priority-pill ${task.priority.toLowerCase()}`}>{task.priority} priority</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="dashboard-detail-card">
                    <div className="dashboard-detail-heading"><Mail size={16} /><span>Mailbox</span><strong>{emailRows.length}</strong></div>
                    <p>{emailRows.length ? "Unread emails" : "No unread emails returned"}</p>
                    {emailRows.slice(0, 3).map((email) => (
                      <div key={email.subject} className="dashboard-detail-item">
                        <span>{email.subject}</span>
                        <small className={`priority-pill ${email.priority.toLowerCase()}`}>{email.priority}</small>
                      </div>
                    ))}
                    <button type="button" className="text-link" onClick={handleViewUnreadEmails}>View unread emails</button>
                  </div>

                  <div className="dashboard-detail-card">
                    <div className="dashboard-detail-heading"><CalendarDays size={16} /><span>Meetings</span><strong>{meetingPreview.length}</strong></div>
                    <p>{meetingPreview.length ? "Upcoming calendar events" : "No upcoming meetings"}</p>
                    {meetingPreview.slice(0, 2).map((meeting) => (
                      <div key={`${meeting.start}-${meeting.subject}`} className="dashboard-detail-item">
                        <span>{meeting.subject}</span>
                        <small>{meeting.start}</small>
                      </div>
                    ))}
                    <button type="button" className="text-link" onClick={() => handleSidebarToolClick("meeting")}>Open MeetMate</button>
                  </div>

                  <div className="dashboard-detail-card">
                    <div className="dashboard-detail-heading"><BriefcaseBusiness size={16} /><span>Jira delivery</span><strong>{jiraIssues.length}</strong></div>
                    <p>{jiraIssues.length ? "Recently updated issues" : "No Jira issues returned"}</p>
                    {jiraIssues.slice(0, 2).map((issue) => (
                      <div key={issue.key} className="dashboard-detail-item">
                        <span>{issue.key}: {issue.summary}</span>
                        <small>{issue.status}</small>
                      </div>
                    ))}
                    <button type="button" className="text-link" onClick={() => handleSidebarToolClick("jira")}>Open Jira</button>
                  </div>

                  <div className="dashboard-detail-card">
                    <div className="dashboard-detail-heading"><FileText size={16} /><span>Document Analyzer</span><strong>{dashboardMetrics.knowledge_documents}</strong></div>
                    <p>{dashboardMetrics.knowledge_documents ? "Indexed knowledge documents" : "No documents loaded"}</p>
                    <button type="button" className="text-link" onClick={() => handleSidebarToolClick("document")}>Open Document Analyzer</button>
                  </div>

                  <div className="dashboard-detail-card">
                    <div className="dashboard-detail-heading"><FolderOpen size={16} /><span>Confluence</span><strong>{confluencePreview.length}</strong></div>
                    <p>{confluencePreview.length ? "Recent matching pages" : "No Confluence pages returned"}</p>
                    {confluencePreview.slice(0, 2).map((page) => (
                      <div key={page} className="dashboard-detail-item"><span>{page}</span></div>
                    ))}
                    <button type="button" className="text-link" onClick={() => handleSidebarToolClick("confluence")}>Open Confluence</button>
                  </div>

                  <div className="dashboard-detail-card">
                    <div className="dashboard-detail-heading"><Bot size={16} /><span>AskBank</span><strong>{dashboardMetrics.integration_status?.AskBank ? "Available" : "Offline"}</strong></div>
                    <p>{dashboardMetrics.integration_status?.AskBank ? "Language model connected" : "Language model is not configured"}</p>
                    <button type="button" className="text-link" onClick={() => handleSidebarToolClick("assistant")}>Open AskBank</button>
                  </div>
                </div>
              </div>
              <div className="panel-heading">
                <h3>{selectedNav === "documents" ? "Document Workspace" : selectedNav === "knowledge" ? "Knowledge Hub" : "Need more specific help?"}</h3>
                <p>{selectedNav === "documents" ? "Analyze and extract information from uploaded documents" : selectedNav === "knowledge" ? "Search approved policies and workspace knowledge" : "Choose an AI tool below to get started."}</p>
              </div>

              <div className="agent-list">
                {visibleAgents.map(({ id, name, description, accent, icon: Icon, count }) => (
                  <button
                    key={id}
                    type="button"
                    className={`agent-card${selectedAgent === id && !workspaceHome ? " active" : ""}`}
                    onClick={() => handleAgentClick(id)}
                  >
                    <span className={`agent-icon ${accent}`}>
                      <Icon size={18} />
                    </span>

                    <span className="agent-copy">
                      <span className="agent-name-row">
                        <span>{name}</span>
                        {count > 0 && <span className="count-badge">{count}</span>}
                      </span>
                      <span className="agent-description">{description}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>}

            {!workspaceHome && <section className="conversation-panel">
              <input
                ref={documentInputRef}
                type="file"
                hidden
                accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.html,.png,.jpg,.jpeg"
                onChange={handleDocumentUpload}
              />
              <div className="panel-header">
                <div className="panel-header-copy">
                  <span className={`panel-icon ${activeAgent.accent}`}>
                    <activeAgent.icon size={18} />
                  </span>
                  <div>
                    <h3>{activeAgent.name}</h3>
                    <p>{activeAgent.description}</p>
                  </div>
                </div>

                <div className="panel-actions">
                  {!detailPanelOpen && <button type="button" className="secondary-button" onClick={() => setDetailPanelOpen(true)}>Show Details</button>}
                  <button type="button" className="secondary-button" onClick={() => {
                    setMessages([]);
                    setMessage("");
                    setDocumentSummary("");
                    setJiraIssues([]);
                    setConfluenceDetails(null);
                    setConfluencePreview([]);
                    setEmailRows([]);
                    setSelectedEmail(null);
                    setEmailActionItems([]);
                    setEmailDraftLines([]);
                    setStatusMessage(selectedAgent === "document" ? "Document analyzer cleared." : "Chat cleared.");
                  }}>
                    <MessageSquareText size={16} />
                    Clear Chat
                  </button>
                  <button type="button" className="primary-button" onClick={startNewChat}>
                    <Plus size={16} />
                    New Chat
                  </button>
                </div>
              </div>

              <div className="messages">
                {messages.map((messageItem) => (
                  <div
                    key={messageItem.id}
                    className={`message-row ${messageItem.role === "assistant" ? "assistant-row" : "user-row"}`}
                  >
                    <div
                      className={`message-bubble ${
                        messageItem.role === "assistant" ? "assistant-bubble" : "user-bubble"
                      } ${messageItem.role === "assistant" && messageItem.id === 2 ? "wide" : ""}`}
                    >
                      {selectedAgent === "jira" && (messageItem.text.includes("### Jira Issues") || messageItem.text.includes("Jira exact results:")) ? (
                        <div className="jira-results">
                          <div className="jira-results-heading">
                            <span>Recent Jira issues</span>
                            <strong>{jiraIssues.length}</strong>
                          </div>
                          {jiraIssues.map((issue) => (
                            <article key={`${messageItem.id}-${issue.key}`} className="jira-issue-card">
                              <div className="jira-issue-topline">
                                <strong>{issue.key}</strong>
                                <span className="jira-status-pill">{issue.status}</span>
                              </div>
                              <p>{issue.summary}</p>
                              <div className="jira-issue-meta">
                                <span>{issue.project}</span>
                                <span>{issue.assignee}</span>
                                <span>{issue.updated}</span>
                              </div>
                            </article>
                          ))}
                          {!jiraIssues.length && <p className="jira-empty-state">Jira issues could not be formatted.</p>}
                        </div>
                      ) : selectedAgent === "confluence" && messageItem.role === "assistant" && messageItem.text.includes("### Confluence Pages") ? (
                        <div className="confluence-results">
                          <div className="confluence-results-heading">
                            <span>Recent Confluence pages</span>
                            <strong>{parseConfluenceResults(messageItem.text).length}</strong>
                          </div>
                          {parseConfluenceResults(messageItem.text).map((page) => (
                            <button
                              key={`${messageItem.id}-${page.pageId}`}
                              type="button"
                              className={`confluence-result-card${confluenceDetails?.pageId === page.pageId ? " selected" : ""}`}
                              aria-label={`Select Confluence page ${page.title}`}
                              onClick={() => selectConfluencePage(page)}
                            >
                              <div className="confluence-result-copy">
                                <span className="confluence-result-label">CONFLUENCE PAGE</span>
                                <h4>{page.title}</h4>
                                <p>{page.preview}</p>
                                <span className="confluence-result-id">Page ID: {page.pageId}</span>
                              </div>
                              <span className="secondary-button">
                                Select page
                              </span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="message-text preserved-line-breaks">{messageItem.text}</p>
                      )}

                      {selectedAgent === "email" && emailRows.length > 0 && messageItem.role === "assistant" && (
                        <div className="summary-table-wrapper">
                          <div className="summary-table">
                            <div className="summary-header">
                              <span>From</span>
                              <span>Subject</span>
                              <span>Priority</span>
                              <span>Summary</span>
                            </div>

                            {emailRows.map((email) => (
                              <button
                                key={`${email.sender}-${email.subject}`}
                                type="button"
                                className="summary-row"
                                onClick={() => handleEmailSelection(email)}
                              >
                                <span>{email.sender}</span>
                                <span>{email.subject}</span>
                                <span>
                                  <span className={`priority-pill ${email.priority.toLowerCase()}`}>{email.priority}</span>
                                </span>
                                <span>{email.summary || "No preview available."}</span>
                              </button>
                            ))}
                          </div>
                          <p className="helper-text">You can click on any email to see full details, extract action items, or draft a response.</p>
                        </div>
                      )}
                    </div>
                    <div className="message-time">{messageItem.time}</div>
                  </div>
                ))}
              </div>

              <div className="quick-actions">
                {selectedAgent === "document" ? (
                  <div className="document-upload-panel">
                    <div className="document-upload-header">
                      <FileText size={16} />
                      <span>Upload a new document for analysis</span>
                    </div>
                    <button
                      type="button"
                      className="primary-button wide"
                      onClick={() => documentInputRef.current?.click()}
                      disabled={documentProcessing}
                    >
                      {documentProcessing ? "Analyzing..." : <><Plus size={16} /> Choose file</>}
                    </button>
                    {documentProcessing && (
                      <div className="document-processing-status" role="status" aria-live="polite">
                        <span className="processing-spinner" aria-hidden="true" />
                        <span>{documentProcessingStages[documentProcessingStage]}</span>
                      </div>
                    )}
                    {documentSummary && (
                        <div className="document-summary-box">
                          <p className="preserved-line-breaks">{documentSummary}</p>
                      </div>
                    )}
                  </div>
                ) : selectedAgent === "email" ? (
                  <>
                    <button type="button" className="chip-button" onClick={handleNewEmailDraft} disabled={isLoading}>
                      <PencilLine size={16} />
                      Draft Email
                    </button>
                    <button type="button" className="chip-button" onClick={handleEmailDraft}>
                      <PencilLine size={16} />
                      Draft Response
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Only show high priority messages.")}>
                      <ShieldCheck size={16} />
                      High Priority Emails Only
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show emails with attachments.")}>
                      <Mail size={16} />
                      Mail With Attachments
                    </button>
                    <button type="button" className="chip-button" onClick={() => void handleEmailSearch()} disabled={isLoading}>
                      <Mail size={16} />
                      Search Unread Mail
                    </button>
                  </>
                ) : selectedAgent === "meeting" ? (
                  <>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show upcoming calendar meetings.")}>
                      <CalendarDays size={16} />
                      Show Upcoming Meetings
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Open Microsoft Teams")}>
                      <MessageSquareText size={16} />
                      Open Teams
                    </button>
                    <button
                      type="button"
                      className="chip-button"
                      onClick={handleScheduleMeeting}
                      disabled={isLoading}
                    >
                      <PencilLine size={16} />
                      Schedule Meeting
                    </button>
                  </>
                ) : selectedAgent === "jira" ? (
                  <>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show Jira stories") }>
                      <BriefcaseBusiness size={16} />
                      Show Jira Stories
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show Jira tasks")}>
                      <CheckCheck size={16} />
                      Show Jira Tasks
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show my assigned Jira issues")}>
                      <ShieldCheck size={16} />
                      My Assigned Work
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show recent Jira sprint items")}>
                      <CalendarDays size={16} />
                      Recent Sprint Items
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show open Jira blockers")}>
                      <ShieldCheck size={16} />
                      Show open Jira blockers
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show Jira bugs")}>
                      <BriefcaseBusiness size={16} />
                      Show Jira bugs
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show current sprint status")}>
                      <CalendarDays size={16} />
                      Show current sprint status
                    </button>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Show Jira sprint summary")}>
                      <BriefcaseBusiness size={16} />
                      Sprint Summary
                    </button>
                    <button type="button" className="chip-button" onClick={() => setMessage("Create a task: Add the next action item for this sprint.")}>
                      <Plus size={16} />
                      Create Task
                    </button>
                    <button type="button" className="chip-button" onClick={() => setMessage("Create a user story: As a banker, I want to review the next priority item so that I can take action quickly.")}>
                      <PencilLine size={16} />
                      Create User Story
                    </button>
                    <button type="button" className="chip-button" onClick={() => setMessage("Analyze story: As a banker, I want to review the high-priority task so that I can resolve the issue quickly.")}>
                      <CheckCheck size={16} />
                      Analyze Story
                    </button>
                  </>
                ) : selectedAgent === "confluence" ? (
                  <>
                    <button type="button" className="chip-button" onClick={() => void submitMessage("Search Confluence pages for recent workspace updates.")}>
                      <BookOpen size={16} />
                      Search Recent Pages
                    </button>
                    <button type="button" className="chip-button" onClick={startConfluenceCreate} disabled={isLoading}>
                      <Plus size={16} />
                      Create Page
                    </button>
                    <button type="button" className="chip-button" onClick={startConfluenceUpdate} disabled={isLoading}>
                      <PencilLine size={16} />
                      Update Page
                    </button>
                    <button type="button" className="chip-button" onClick={() => void createJiraStoryFromConfluence()} disabled={isLoading || !hasSelectedConfluencePage}>
                      <BriefcaseBusiness size={16} />
                      Create Jira Story
                    </button>
                  </>
                ) : null}
              </div>

              {selectedAgent !== "document" && (
                <form onSubmit={handleSubmit} className="composer">
                  <label htmlFor="message">Type your message to {activeAgent.name}...</label>
                  <div className="composer-box">
                    <div className="composer-tools">
                      <button type="button" className="mini-button" aria-label="Attach file" onClick={() => documentInputRef.current?.click()}>
                        <Plus size={16} />
                      </button>
                      <button type="button" className="mini-button" aria-label="Add emoji" onClick={() => setMessage((current) => `${current} 🙂`.trimStart())}>
                        <Sparkles size={16} />
                      </button>
                    </div>
                    <textarea
                      id="message"
                      name="message"
                      value={message}
                      onChange={(event) => setMessage(event.target.value)}
                      onKeyDown={handleMessageKeyDown}
                      placeholder={`Type your message to ${activeAgent.name}...`}
                    />
                    <button type="submit" className="send-button" disabled={isLoading} aria-label="Send message">
                      <ArrowRight size={18} />
                    </button>
                  </div>
                </form>
              )}
            </section>}

            {!workspaceHome && detailPanelOpen && selectedAgent !== "document" && <aside className="detail-panel">
              <div className="detail-card">
                <div className="detail-header">
                  <div className="detail-heading">
                    {activeAgent.icon ? <activeAgent.icon size={16} /> : <Mail size={16} />}
                    <span>{activeDetail.title}</span>
                  </div>
                  <button type="button" className="detail-close" aria-label="Close panel" onClick={() => setDetailPanelOpen(false)}>
                    ×
                  </button>
                </div>

                <dl className="detail-list">
                  {(selectedAgent === "jira" && jiraIssues.length > 0
                    ? [
                        { label: "Issues", value: `${jiraIssues.length} loaded` },
                        { label: "Project", value: [...new Set(jiraIssues.map((issue) => issue.project))].join(", ") },
                        { label: "Statuses", value: [...new Set(jiraIssues.map((issue) => issue.status))].join(", ") },
                        { label: "Assignees", value: [...new Set(jiraIssues.map((issue) => issue.assignee))].join(", ") },
                      ]
                    : activeDetail.detailItems
                  ).map(({ label, value }) => (
                    <div key={label} className="detail-row">
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              <div className="detail-card">
                <div className="detail-header">
                  <div className="detail-heading">
                    <MessageSquareText size={16} />
                    <span>{selectedAgent === "email" ? "Email Summary" : `${activeAgent.name} Summary`}</span>
                  </div>
                </div>
                <p className="summary-copy">{activeDetail.summary}</p>
              </div>

              {(selectedAgent !== "email" || emailDraftLines.length > 0) && <div className="detail-card draft-card">
                <div className="detail-header">
                  <div className="detail-heading">
                    <PencilLine size={16} />
                    <span>{selectedAgent === "confluence" ? "Suggested Confluence Page" : "Suggested Response (Draft)"}</span>
                  </div>
                  <button type="button" className="utility-button" aria-label="Copy response" onClick={copyDraft}>
                    <Copy size={15} />
                    Copy
                  </button>
                </div>

                <div className="draft-content">
                  {activeDetail.draftLines.map((line, index) => (
                    <p key={`${line}-${index}`}>{line}</p>
                  ))}
                </div>

                <div className="draft-actions">
                  <button type="button" className="secondary-button wide" onClick={editDraft}>
                    <PencilLine size={16} />
                    Edit
                  </button>
                  <button
                    type="button"
                    className="primary-button wide"
                    onClick={handleUtilityAction}
                  >
                    <ArrowRight size={16} />
                    {selectedAgent === "email"
                      ? emailDraftLines.length
                        ? selectedEmail ? "Send via Outlook" : "Edit Draft"
                        : selectedEmail ? "Draft Response" : "Draft Email"
                      : selectedAgent === "meeting" ? "Open Microsoft Teams" : selectedAgent === "confluence" ? "Update selected page" : `Send via ${activeAgent.name}`}
                  </button>
                </div>
              </div>}
            </aside>}
          </div>
        )}
      </section>
    </main>
  );
}
