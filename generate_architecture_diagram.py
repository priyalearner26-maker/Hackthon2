from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

out_png = Path("architecture_diagram.png")
out_svg = Path("architecture_diagram.svg")

fig, ax = plt.subplots(figsize=(19, 10.8))
fig.patch.set_facecolor("#dff1f4")
ax.set_xlim(0, 18)
ax.set_ylim(0, 11)
ax.axis("off")
ax.set_aspect('equal', adjustable='box')


def add_box(x, y, w, h, title, body, fc="#dff1f4", ec="#1f2937", title_color="#0f172a", body_color="#1f2937", title_size=12, body_size=9, linewidth=1.6, radius=0.12):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.03,rounding_size={radius}",
        linewidth=linewidth,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    if title:
        ax.text(
            x + w / 2,
            y + h * 0.72,
            title,
            ha="center",
            va="center",
            fontsize=title_size,
            fontweight="bold",
            color=title_color,
        )
    if body:
        ax.text(
            x + w / 2,
            y + h * 0.38,
            body,
            ha="center",
            va="center",
            fontsize=body_size,
            color=body_color,
            linespacing=1.35,
            fontweight="normal",
        )


def add_left_list_box(x, y, w, h, title, items, fc="#d9ecef", ec="#2a5f77", title_color="#0f172a", body_color="#1f2937"):
    add_box(x, y, w, h, title, "", fc=fc, ec=ec, title_color=title_color, body_color=body_color, title_size=14)
    start_y = y + h - 0.70
    for idx, item in enumerate(items):
        text_y = start_y - idx * 0.42
        ax.text(x + 0.22, text_y, item, fontsize=9, color="#0f172a", va="center")


def add_small_bullet_box(x, y, w, h, title, items, fc="#eaf4f8", ec="#2a5f77", title_size=10, body_size=8):
    add_box(x, y, w, h, title, "", fc=fc, ec=ec, title_color="#0f172a", body_color="#1f2937", title_size=title_size, body_size=body_size)
    start_y = y + h - 0.45
    for idx, item in enumerate(items):
        ax.text(x + 0.18, start_y - idx * 0.24, "• " + item, fontsize=body_size, color="#0f172a", va="center")


def add_arrow(start, end, text=None, color="#334155", style="-", lw=1.4, arrow_size=15):
    arrow = FancyArrowPatch(
        start, end,
        arrowstyle="-|>",
        mutation_scale=arrow_size,
        linewidth=lw,
        color=color,
        linestyle=style,
    )
    ax.add_patch(arrow)
    if text:
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ax.text(mid_x, mid_y + 0.12, text, fontsize=8, ha="center", color="#1f2937")


# Header
header = FancyBboxPatch((0.2, 10.15), 17.6, 0.75, boxstyle="round,pad=0.02,rounding_size=0.15", linewidth=0, facecolor="#2c5d8d")
ax.add_patch(header)
ax.text(1.0, 10.55, "BANK", fontsize=16, fontweight="bold", color="white")
ax.text(1.0, 10.32, "Bank Employee AI Workspace", fontsize=14, fontweight="bold", color="white")
ax.text(6.0, 10.55, "Current Runtime Architecture", fontsize=16, fontweight="bold", color="white")
ax.text(6.0, 10.28, "MailMate, MeetMate, Jira/Confluence, Document Analysis, RAG and AskBank", fontsize=9, color="#e7f3ff")

badge = FancyBboxPatch((15.2, 10.22), 2.0, 0.5, boxstyle="round,pad=0.02,rounding_size=0.12", linewidth=0, facecolor="#c7ddec")
ax.add_patch(badge)
ax.text(16.2, 10.47, '"Work Smarter', fontsize=8, fontweight="bold", color="#0f172a")
ax.text(16.2, 10.28, 'Serve Better"', fontsize=8, fontweight="bold", color="#0f172a")

# Left panel
add_left_list_box(
    0.3,
    2.4,
    2.5,
    6.7,
    "Bank Employee",
    [
        "Employee / Operator",
        "Employee UI (Next.js)",
        "Chat Workspace",
        "Email Assistant",
        "Meeting Assistant",
        "Jira & Confluence",
        "Document Q&A",
        "Dashboard",
        "Unread mail search",
        "Draft and send email",
        "No active SSO/RBAC yet",
    ],
    fc="#cbeadf",
    ec="#1f5d7a",
)

# Add left panel header line for first item spacing to mimic reference
ax.text(1.1, 9.0, "People", fontsize=9, color="#0f172a", fontweight="bold")
ax.text(1.1, 8.8, "|", fontsize=9, color="#0f172a")

# API layer
add_box(3.4, 5.5, 4.2, 4.4, "API & Application Layer\n(FastAPI)", "", fc="#d5f0d5", ec="#1f9c8b", title_size=13)
api_items = [
    "Chat API routes",
    "Email API routes",
    "Calendar via agent",
    "Jira/Confluence via agent",
    "Document upload + analysis",
    "Dashboard API routes",
    "CORS + request middleware",
    "Stable error responses",
]
for idx, item in enumerate(api_items):
    y_pos = 8.45 - idx * 0.44
    ax.text(3.95, y_pos, item, fontsize=8, color="#0f172a", va="center")

# Supervisor
add_box(8.2, 5.5, 4.0, 4.4, "LangGraph Supervisor\n(Agent Orchestrator)", "", fc="#f5e7cd", ec="#d5a63f", title_size=13)
supervisor_items = [
    "Classify request",
    "Retrieve approved knowledge",
    "Route to specialist",
    "Return user-facing response",
    "No persistent session memory",
]
for idx, item in enumerate(supervisor_items):
    y_pos = 8.1 - idx * 0.44
    ax.text(8.55, y_pos, "• " + item, fontsize=8, color="#0f172a", va="center")

# Specialist agents
add_box(12.7, 5.5, 3.1, 4.4, "Specialist Agents\n(Essential)", "", fc="#f8dada", ec="#d45b6a", title_size=13)
agent_items = [
    "MailMate\nOutlook / Graph",
    "MeetMate\nOutlook / Graph / local calendar",
    "JiraPilot + Confluence Coach",
    "Document Analyzer",
    "AskBank\nOpenAI / Ollama",
]
for idx, item in enumerate(agent_items):
    y_pos = 8.45 - idx * 0.62
    ax.text(13.2, y_pos, item, fontsize=8, color="#0f172a", va="center")

# External services header style alignment
add_box(16.1, 5.5, 1.8, 4.4, "External Services\n& Integrations", "", fc="#dfeaf7", ec="#515ee4", title_size=11)

# Independent browser-test application. It is deliberately shown outside the
# FastAPI and Next.js application path to make the deployment boundary explicit.
add_box(
    12.7,
    3.95,
    3.1,
    1.05,
    "Playwright Test Command",
    "Independent Vite UI + Express API\nSocket.IO events • browser matrix • Allure artifacts",
    fc="#d9f2e3",
    ec="#23866a",
    title_color="#14543f",
    body_color="#245344",
    title_size=11,
    body_size=7.5,
)

# External services contents
services = [
    "Classic Outlook / Graph Mail",
    "Teams launcher",
    "Jira",
    "Confluence",
    "OpenAI embeddings",
    "Ollama",
    "Local JSON calendar",
]
for idx, item in enumerate(services):
    y_pos = 8.45 - idx * 0.52
    ax.text(17.0, y_pos, item, fontsize=7.5, color="#0f172a", ha="center", va="center")

# Knowledge and retrieval layer
add_box(7.0, 2.1, 5.1, 1.8, "Knowledge & Retrieval\n(RAG Layer)", "KnowledgeRetriever\n• Loads approved documents\n• Chroma + FAISS when embeddings are configured\n• Lexical fallback with citations\n• Metadata filtering", fc="#dce6ff", ec="#4f46e5", title_size=12, body_size=8)

# Sources panel
sources = [
    "Internal Knowledge Base\n• Policies & procedures\n• Process documents\n• Architecture & API contracts",
    "Incoming Documents\n• PDF, Word, Excel, PPT\n• Meeting notes\n• Circulars & Memos",
    "Mail Sources\n• Classic Outlook COM\n• Microsoft Graph\n• Inbox metadata and bodies",
    "Calendar Sources\n• Outlook calendar\n• Microsoft Graph\n• Local workspace calendar",
    "Confluence\n• Search and page retrieval\n• Page creation and updates\n• Ingestion into RAG",
    "Jira\n• JQL issue search\n• Story analysis\n• Task/story creation",
    "Vector Store / Index\n• ChromaDB embeddings\n• FAISS cosine search\n• Local chunks fallback",
]

source_x_start = 0.3
source_w = 2.2
for idx, text in enumerate(sources):
    x = source_x_start + idx * 2.45
    add_box(x, 0.25, source_w, 1.45, "", text, fc="#dff3d7", ec="#5aa75a", title_color="#0f172a", body_color="#0f172a", title_size=8, body_size=7, linewidth=1.1)

# Bottom utility boxes
add_box(0.5, 0.15, 2.2, 0.85, "", "Local privacy boundary\nMailbox data stays in the\nconfigured integration", fc="#eadbf5", ec="#8b5cf6", title_size=10, body_size=8)
add_box(2.9, 0.15, 2.4, 0.85, "", "Configuration\n.env settings\nProvider credentials", fc="#e7e1ff", ec="#8b5cf6", title_size=10, body_size=8)
add_box(5.5, 0.15, 2.3, 0.85, "", "Request middleware\nRequest IDs\nTiming + error logging", fc="#e7e1ff", ec="#8b5cf6", title_size=10, body_size=8)
add_box(8.0, 0.15, 2.3, 0.85, "", "Development\nDocker Compose\nLocal uvicorn + Next.js", fc="#e7e1ff", ec="#8b5cf6", title_size=10, body_size=8)
add_box(10.5, 0.15, 2.2, 0.85, "", "Storage\nChromaDB / JSON chunks\nUploaded documents", fc="#e7e1ff", ec="#8b5cf6", title_size=10, body_size=8)
add_box(12.9, 0.15, 4.2, 0.85, "", "Current outcome\nOperational employee workspace\nwith live integration fallbacks", fc="#e7e1ff", ec="#8b5cf6", title_size=10, body_size=8)

# arrows between main blocks
add_arrow((7.6, 6.7), (8.2, 6.7), text="requests", color="#334155", lw=1.5)
add_arrow((12.2, 6.7), (12.7, 6.7), text="route to agents", color="#334155", lw=1.5)
add_arrow((10.2, 5.5), (10.2, 3.9), text="retrieval", color="#334155", lw=1.5)
add_arrow((8.7, 2.1), (8.7, 1.1), text="documents", color="#334155", lw=1.5, style="--")
add_arrow((11.6, 2.1), (11.6, 1.1), text="vector index", color="#334155", lw=1.5, style="--")
add_arrow((5.0, 5.5), (3.4, 5.5), text="API response", color="#334155", lw=1.5)
add_arrow((2.4, 5.2), (3.4, 5.2), text="", color="#334155", lw=1.5)
add_arrow((2.8, 4.45), (12.7, 4.45), text="independent test execution boundary", color="#23866a", lw=1.2, style="--")

# frame for top quality feel
frame = FancyBboxPatch((0.15, 0.05), 17.7, 10.7, boxstyle="round,pad=0.02,rounding_size=0.18", linewidth=1.2, edgecolor="#7eb1ce", facecolor="none")
ax.add_patch(frame)

fig.savefig(out_png, dpi=180, bbox_inches="tight")
fig.savefig(out_svg, bbox_inches="tight")
print(f"Saved diagram to {out_png.resolve()}")
print(f"Saved diagram to {out_svg.resolve()}")
