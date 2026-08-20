/**
 * Semantic Scholar client.
 * Routes via FastAPI backend search proxy (/api/papers/search) to bypass browser CORS restrictions.
 */
import type { Paper } from "@/lib/types";

const BACKEND_URL = import.meta.env.VITE_RAG_BACKEND_URL || "http://localhost:8000";
const DIRECT_BASE = "https://api.semanticscholar.org/graph/v1";
const SS_KEY = import.meta.env.VITE_SEMANTIC_SCHOLAR_API_KEY as string | undefined;

const ssHeaders = (): HeadersInit => (SS_KEY ? { "x-api-key": SS_KEY } : {});
const FIELDS = [
  "paperId",
  "externalIds",
  "title",
  "abstract",
  "year",
  "authors.name",
  "citationCount",
  "openAccessPdf",
].join(",");

interface SSAuthor { name: string }
interface SSPaper {
  paperId: string;
  externalIds?: { DOI?: string; ArXiv?: string };
  title: string;
  abstract: string | null;
  year: number | null;
  authors: SSAuthor[];
  citationCount: number;
  openAccessPdf: { url: string } | null;
}

const toPaper = (p: SSPaper): Paper => ({
  id: p.paperId, // temporary id used for UI; persisted papers will get real uuid
  doi: p.externalIds?.DOI ?? null,
  title: p.title,
  authors: (p.authors ?? []).map((a) => a.name),
  year: p.year ?? null,
  abstract: p.abstract,
  citation_count: p.citationCount ?? 0,
  open_access_url: p.openAccessPdf?.url ?? null,
  semantic_scholar_id: p.paperId,
  arxiv_id: p.externalIds?.ArXiv ?? null,
});

export async function searchPapers(query: string, limit = 20): Promise<Paper[]> {
  if (!query.trim()) return [];

  // Route via FastAPI Backend Search Proxy (Bypasses Browser CORS)
  const proxyUrl = `${BACKEND_URL}/api/papers/search?query=${encodeURIComponent(query)}&limit=${limit}`;
  const res = await fetch(proxyUrl);
  if (res.ok) {
    const json = await res.json();
    const data = (json.data ?? []) as SSPaper[];
    return data.map(toPaper);
  }

  let errorDetail = `Search request failed with status ${res.status}`;
  try {
    const errJson = await res.json();
    if (errJson.detail) errorDetail = errJson.detail;
  } catch {
    // Keep generic error detail if JSON parsing fails
  }
  throw new Error(errorDetail);
}

export async function getPaperById(ssId: string): Promise<Paper | null> {
  // Route via FastAPI Backend Search Proxy
  const proxyUrl = `${BACKEND_URL}/api/papers/${ssId}`;
  const res = await fetch(proxyUrl);
  if (res.ok) {
    const p = (await res.json()) as SSPaper;
    return toPaper(p);
  }
  if (res.status === 404) {
    return null;
  }

  let errorDetail = `Paper fetch failed with status ${res.status}`;
  try {
    const errJson = await res.json();
    if (errJson.detail) errorDetail = errJson.detail;
  } catch {
    // Keep generic error detail if JSON parsing fails
  }
  throw new Error(errorDetail);
}
