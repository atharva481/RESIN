/**
 * Semantic Scholar client. Public API, no key required for low traffic.
 * Docs: https://api.semanticscholar.org/graph/v1
 */
import type { Paper } from "@/lib/types";

const BASE = "https://api.semanticscholar.org/graph/v1";
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
  const url = `${BASE}/paper/search?query=${encodeURIComponent(query)}&limit=${limit}&fields=${FIELDS}`;
  const res = await fetch(url, { headers: ssHeaders() });
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("Too many requests (Rate limited). Semantic Scholar's public API is strict. Please try again in a few minutes, or add VITE_SEMANTIC_SCHOLAR_API_KEY to your .env file for higher limits.");
    }
    throw new Error(`Semantic Scholar search failed (${res.status})`);
  }
  const json = await res.json();
  const data = (json.data ?? []) as SSPaper[];
  return data.map(toPaper);
}

export async function getPaperById(ssId: string): Promise<Paper | null> {
  const res = await fetch(`${BASE}/paper/${ssId}?fields=${FIELDS}`, { headers: ssHeaders() });
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("Too many requests (Rate limited). Please try again later or add an API key.");
    }
    return null;
  }
  const p = (await res.json()) as SSPaper;
  return toPaper(p);
}
