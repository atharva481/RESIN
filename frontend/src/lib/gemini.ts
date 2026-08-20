/**
 * Gemini client (browser-side, optional).
 * For production, move this to a Supabase Edge Function so the API key isn't shipped.
 * Set VITE_GEMINI_API_KEY in `.env`.
 */
import type { PaperSummary } from "@/lib/types";

const KEY = import.meta.env.VITE_GEMINI_API_KEY as string | undefined;
const MODEL = "gemini-flash-latest";

export const isGeminiConfigured = Boolean(KEY);

interface GeminiResponse {
  candidates?: { content?: { parts?: { text?: string }[] } }[];
}

async function callGemini(prompt: string): Promise<string> {
  if (!KEY) throw new Error("Gemini API key missing — set VITE_GEMINI_API_KEY in .env");
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${KEY}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.3, responseMimeType: "application/json" },
    }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Gemini failed (${res.status}): ${t}`);
  }
  const json = (await res.json()) as GeminiResponse;
  return json.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
}

export async function generatePaperSummary(args: {
  title: string;
  abstract: string | null;
  authors: string[];
  year: number | null;
}): Promise<Omit<PaperSummary, "paper_id" | "generated_at">> {
  const prompt = `You are a research analyst. Read the paper metadata and produce a clear, plain-English structured digest.

Rules:
- Avoid jargon. Be concise and factual.
- Each field must be 1–3 sentences only.
- Do NOT add any text outside the JSON.
- If information is missing, infer cautiously or state "Not واضح from provided data".

Return STRICT JSON with exactly these keys:
{
  "problem": "",
  "method": "",
  "findings": "",
  "limitations": "",
  "significance": ""
}

PAPER:
Title: ${args.title}
Authors: ${args.authors.join(", ")}
Year: ${args.year ?? "n/a"}
Abstract: ${args.abstract ?? "(no abstract available — infer from title)"}
`;

  const text = await callGemini(prompt);
  try {
    const obj = JSON.parse(text);
    return {
      problem: obj.problem ?? null,
      method: obj.method ?? null,
      findings: obj.findings ?? null,
      limitations: obj.limitations ?? null,
      significance: obj.significance ?? null,
    };
  } catch {
    return { problem: text, method: null, findings: null, limitations: null, significance: null };
  }
}

export async function summariseArticle(title: string, description: string | null): Promise<string> {
  if (!KEY) return description ?? "";
  const prompt = `Summarize the following tech news article in EXACTLY 2 sentences and no more than 35 words total. Keep language simple, neutral, and factual. No hype, no opinions, no extra details.

Title: ${title}
Description: ${description ?? ""}

Return only the 2-sentence summary as plain text.`;
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${KEY}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contents: [{ role: "user", parts: [{ text: prompt }] }] }),
  });
  if (!res.ok) return description ?? "";
  const json = (await res.json()) as GeminiResponse;
  return json.candidates?.[0]?.content?.parts?.[0]?.text?.trim() ?? description ?? "";
}
