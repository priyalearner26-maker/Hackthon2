const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function sendMessage(sessionId: string, message: string, agent?: string) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, agent }),
  });

  if (!response.ok) {
    throw new Error("Unable to send message");
  }

  return response.json() as Promise<{ session_id: string; answer: string; route?: string }>;
}

export async function ingestConfluencePage(pageUrl: string) {
  const response = await fetch(`${API_BASE_URL}/knowledge/confluence/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_url: pageUrl }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to ingest Confluence page");
  return payload as { status: string; source: string; chunks: number };
}

export async function createConfluencePage(title: string, content: string) {
  const response = await fetch(`${API_BASE_URL}/knowledge/confluence/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, content }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to create Confluence page");
  return payload as { status: string; message: string; url: string };
}

export async function createJiraIssue(issueType: "Task" | "Story", summary: string) {
  const response = await fetch(`${API_BASE_URL}/jira/issues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ issue_type: issueType, summary }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to create Jira issue");
  return payload as { status: string; message: string; url: string };
}

export type JiraTestCase = {
  name: string;
  objective: string;
  preconditions: string;
  steps: string[];
  test_data: string;
  expected_result: string;
  priority: "Highest" | "High" | "Medium" | "Low";
};

export async function getJiraStory(issueKey: string) {
  const response = await fetch(`${API_BASE_URL}/jira/issues/${encodeURIComponent(issueKey)}`, { cache: "no-store" });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to load Jira story");
  return payload as {
    key: string;
    title: string;
    description: string;
    acceptance_criteria: string;
    metadata: { issue_type: string; priority: string; assignee: string; status: string; updated: string; project: string; labels: string[] };
  };
}

export async function generateJiraTestCases(storyKey: string) {
  const response = await fetch(`${API_BASE_URL}/jira/test-cases/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ story_key: storyKey }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to generate Jira test cases");
  return payload as { story: Awaited<ReturnType<typeof getJiraStory>>; test_cases: JiraTestCase[] };
}

export async function createJiraTestCases(storyKey: string, testCases: JiraTestCase[]) {
  const response = await fetch(`${API_BASE_URL}/jira/test-cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ story_key: storyKey, test_cases: testCases }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to create Jira test cases");
  return payload as { status: string; story_key: string; created: Array<{ key: string; url: string }> };
}

export async function sendEmail(recipient: string, subject: string, body: string) {
  const response = await fetch(`${API_BASE_URL}/email/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient, subject, body }),
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Unable to send email");
  }

  return response.json() as Promise<{ status: string; recipient: string; provider: string }>;
}

export async function getEmailMessages(unreadOnly = true, query = "") {
  const params = new URLSearchParams({ unread_only: String(unreadOnly) });
  if (query.trim()) params.set("query", query.trim());
  const response = await fetch(`${API_BASE_URL}/email/messages?${params.toString()}`, { cache: "no-store" });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail ?? "Unable to load mailbox");
  return payload as {
    messages: Array<{
      id: string;
      subject: string;
      sender: string;
      sender_email: string;
      received_at: string;
      body: string;
      priority: string;
      has_attachments: boolean;
      attachment_names: string[];
    }>;
  };
}

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/documents/upload`, { method: "POST", body: formData });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? "Unable to analyze document");
  }
  return payload as {
    status: string;
    document_id: string;
    analysis: {
      filename: string;
      characters: number;
      word_count: number;
      summary: string;
      headings: string[];
      action_items: string[];
      keywords: string[];
    };
  };
}

export async function getDashboardSummary() {
  const response = await fetch(`${API_BASE_URL}/dashboard/summary`, { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to load dashboard metrics");
  return response.json() as Promise<{
    status: string;
    connected_integrations: number;
    integration_status: Record<string, boolean>;
    knowledge_documents: number;
  }>;
}

export async function searchKnowledge(query: string) {
  const response = await fetch(`${API_BASE_URL}/knowledge/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error("Unable to search approved knowledge");
  }

  return response.json() as Promise<{
    query: string;
    results: Array<{
      citation: string;
      source: string;
      content: string;
      score: number;
      page: number | null;
    }>;
  }>;
}
