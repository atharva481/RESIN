# RESIN Frontend: Research Workstation UI

The user-facing client for **RESIN**, built with React 18, Vite, TypeScript, and Tailwind CSS. It provides an academic-grade workstation interface for searching scientific publications, managing personal research libraries, reading AI-curated daily topic digests, and interacting with page-grounded RAG streams and multi-paper research agents.

---

## 🚀 Key Features & Capabilities

- **Interactive Paper Hub**: Live academic search powered by Semantic Scholar & OpenAlex proxies, with instant citation previews and quick-save capabilities.
- **Section & Page-Aware RAG Drawer (`PaperChat`)**:
  - Connects to FastAPI `/api/chat/stream` via Server-Sent Events (SSE).
  - Real-time token rendering with an average Time-to-First-Token (TTFT) of ~1.1 seconds.
  - Interactive page-number citation pills (`Page 3`, `Section: Methods`) that link directly to the source text.
- **Resilient AI Summaries (`lib/gemini.ts`)**:
  - 5-point structured abstract digest (Problem, Method, Findings, Limitations, Significance).
  - Built-in `503 Service Unavailable` demand spike handling with automatic jittered retry and multi-candidate model failover (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-flash-lite-latest`, `gemini-flash-latest`).
- **Autonomous Multi-Paper Research Agent UI (`Agent.tsx`)**:
  - Interactive multi-turn chat with ReAct tool-execution logs.
  - Real-time display of cross-paper comparisons and literature syntheses.
- **Personal Library & Reference Exports (`Library.tsx`)**:
  - Custom folder categorization and reading status management (`unread`, `in_progress`, `done`).
  - One-click reference exports to BibTeX, APA, and MLA formats.
- **Daily Research Triage (`DailyTriageSection`)**:
  - Automated "Today's Top Reads" banner highlighting AI-curated daily papers tailored to the user's research topics.

---

## 🛠 Tech Stack

- **Core**: React 18, TypeScript, Vite
- **Styling**: Tailwind CSS, Shadcn UI primitives, Lucide Icons, Sonner (toast notifications)
- **Data Fetching & State**: TanStack Query (React Query) v5
- **Authentication & Database**: Supabase JS Client (v2) with Row Level Security (RLS)
- **Markdown & Code Highlighting**: `react-markdown`, `remark-gfm`

---

## ⚙️ Setup & Development

### 1. Prerequisites
- Node.js 18+ and npm

### 2. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure the following variables are configured:
```bash
VITE_SUPABASE_URL="https://your-project.supabase.co"
VITE_SUPABASE_ANON_KEY="your-anon-key"
VITE_RAG_BACKEND_URL="http://localhost:8000"
VITE_GEMINI_API_KEY="your-gemini-api-key"
```

### 3. Install Dependencies
```bash
npm install
```

### 4. Run Development Server
```bash
npm run dev
```
The application will launch at `http://localhost:5173` (or port configured in `vite.config.ts`).

### 5. Build for Production
```bash
npm run build
```
Type checks the project and outputs optimized static bundles to `dist/`.
