/**
 * NewsAPI.org client. Requires VITE_NEWS_API_KEY in .env.
 * Free dev keys are localhost-only; for prod, route this through an edge function.
 */
import type { FeedItem } from "@/lib/types";

const KEY = import.meta.env.VITE_NEWS_API_KEY as string | undefined;

interface NewsArticle {
  source: { name: string };
  title: string;
  url: string;
  description: string | null;
  publishedAt: string;
  urlToImage: string | null;
}

const toFeedItem = (a: NewsArticle, topics: string[]): FeedItem => ({
  id: a.url,
  source: a.source?.name ?? "Unknown",
  title: a.title,
  url: a.url,
  summary: a.description,
  published_at: a.publishedAt,
  topics,
  image_url: a.urlToImage,
});

export const isNewsConfigured = Boolean(KEY);

export async function fetchTechNews(query: string, topics: string[] = []): Promise<FeedItem[]> {
  if (!KEY) return [];
  const q = encodeURIComponent(query || "(AI OR machine learning OR robotics OR LLM OR biotech)");
  const url = `https://newsapi.org/v2/everything?q=${q}&language=en&sortBy=publishedAt&pageSize=30&apiKey=${KEY}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`NewsAPI failed (${res.status})`);
  const json = await res.json();
  return (json.articles as NewsArticle[]).map((a) => toFeedItem(a, topics));
}
