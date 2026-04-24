# RESIN: Project Details

## Overview
RESIN is a modern, serverless web application designed to help users discover, organize, and summarize academic research papers. It provides an intuitive interface for searching academic databases, securely saving papers into personalized folders, and leveraging AI to generate structured digests of complex scientific abstracts.

## Technology Stack
- **Frontend Framework**: React 18 with Vite
- **Language**: TypeScript
- **Routing**: React Router v6
- **Styling**: Tailwind CSS (custom "paper" and "ink" design system tokens)
- **UI Components**: Shadcn UI, Lucide React (Icons), Sonner (Toasts)
- **Backend & Database**: Supabase (PostgreSQL, Auto-generated REST APIs)
- **Authentication**: Supabase Auth (Google OAuth integration)
- **External APIs**:
  - Semantic Scholar API (Paper search and metadata)
  - Google Gemini AI (Abstract summarization)
  - NewsAPI (Industry news feed)

## Core Features
1. **Authentication & Security**: Protected routes enforcing login. User data is strictly partitioned using PostgreSQL Row Level Security (RLS) policies.
2. **Paper Hub**: Search functionality connecting directly to the Semantic Scholar public graph to fetch real-time academic data.
3. **Personal Library**:
   - Organize saved papers into custom folders.
   - Track reading status (`unread`, `in_progress`, `done`).
   - Export references to formats like BibTeX, APA, and MLA.
4. **AI Summarization**: Intelligent extraction of key details (Problem, Method, Findings, Limitations, Significance) using Gemini.
5. **Graph View**: Visual connection map of related papers.

## Database Schema (PostgreSQL)

### `users`
- `id`: uuid (Primary Key)
- `email`: text (UNIQUE)
- `topics`: text[]
- `created_at`: timestamptz

### `papers`
Shared dictionary of all papers saved by any user.
- `id`: uuid (Primary Key)
- `doi`: text
- `title`: text (NOT NULL)
- `authors`: text[]
- `year`: integer
- `abstract`: text
- `citation_count`: integer (default 0)
- `open_access_url`: text
- `semantic_scholar_id`: text (UNIQUE)
- `arxiv_id`: text (UNIQUE)
- `updated_at`: timestamptz
- `created_at`: timestamptz

### `folders`
- `id`: uuid (Primary Key)
- `user_id`: uuid (Foreign Key -> users.id)
- `name`: text (NOT NULL)
- `created_at`: timestamptz

### `user_papers`
Join table linking users to their saved papers and folders.
- `id`: uuid (Primary Key)
- `user_id`: uuid (Foreign Key -> users.id)
- `paper_id`: uuid (Foreign Key -> papers.id)
- `folder_id`: uuid (Foreign Key -> folders.id)
- `notes`: text
- `status`: text (default 'unread')
- `saved_at`: timestamptz

### `paper_summaries`
Shared AI summaries generated for papers.
- `paper_id`: uuid (Primary Key, Foreign Key -> papers.id)
- `problem`: text
- `method`: text
- `findings`: text
- `limitations`: text
- `significance`: text
- `generated_at`: timestamptz

## Security (Row Level Security)
The application relies heavily on Supabase RLS to secure data without needing a custom backend server.
- **users**: Users can only select, insert, and update their own records.
- **folders**: Users can manage their own folders based on matching `user_id` with `auth.uid()`.
- **user_papers**: Users can manage their own saved papers based on matching `user_id` with `auth.uid()`.
- **papers**: All authenticated users can insert, update, and select from the shared papers dictionary.
- **paper_summaries**: All authenticated users can manage shared AI summaries.
