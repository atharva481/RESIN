// Domain types mirroring the provided Postgres schema.
export type PaperStatus = "unread" | "in_progress" | "done";

export interface Paper {
  id: string;
  doi: string | null;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  citation_count: number;
  open_access_url: string | null;
  semantic_scholar_id: string | null;
  arxiv_id: string | null;
  updated_at?: string;
  created_at?: string;
}

export interface PaperSummary {
  paper_id: string;
  problem: string | null;
  method: string | null;
  findings: string | null;
  limitations: string | null;
  significance: string | null;
  generated_at?: string;
}

export interface Folder {
  id: string;
  user_id: string;
  name: string;
  created_at?: string;
}

export interface UserPaper {
  id: string;
  user_id: string;
  paper_id: string;
  folder_id: string | null;
  notes: string | null;
  status: PaperStatus;
  saved_at?: string;
}

export interface FeedItem {
  id: string;
  source: string;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  topics: string[];
  image_url: string | null;
  created_at?: string;
}

export interface CitationEdge {
  paper_id_a: string;
  paper_id_b: string;
  edge_type: "direct_citation" | "shared_citation" | "same_author" | "topic_similarity";
  weight: number;
}

// RAG Specific Types
export interface RagCitation {
  section_title?: string;
  chunk_index: number;
  content_snippet: string;
  similarity_score: number;
}

export interface RagChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: RagCitation[];
}

export interface RagChatResponse {
  answer: string;
  citations: RagCitation[];
}

export interface RagIndexResponse {
  paper_id: string;
  chunks_created: number;
  status: "success" | "warning" | "error";
  message: string;
}
