import { supabase } from "./supabase";
import { RagChatMessage, RagChatResponse, RagIndexResponse } from "./types";

const BACKEND_URL = import.meta.env.VITE_RAG_BACKEND_URL || "http://localhost:8000";

async function getAuthHeader(): Promise<HeadersInit> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface IndexPaperOptions {
  fullText?: string;
  force?: boolean;
  title?: string;
  doi?: string | null;
  arxivId?: string | null;
  openAccessUrl?: string | null;
  abstract?: string | null;
}

export async function indexPaper(
  paperId: string,
  optionsOrFullText?: string | IndexPaperOptions,
  force = false
): Promise<RagIndexResponse> {
  const headers = await getAuthHeader();

  let bodyPayload: Record<string, any> = {
    paper_id: paperId,
    force,
  };

  if (typeof optionsOrFullText === "string") {
    bodyPayload.full_text = optionsOrFullText;
  } else if (optionsOrFullText && typeof optionsOrFullText === "object") {
    bodyPayload = {
      paper_id: paperId,
      full_text: optionsOrFullText.fullText,
      force: optionsOrFullText.force ?? force,
      title: optionsOrFullText.title,
      doi: optionsOrFullText.doi ?? undefined,
      arxiv_id: optionsOrFullText.arxivId ?? undefined,
      open_access_url: optionsOrFullText.openAccessUrl ?? undefined,
      abstract: optionsOrFullText.abstract ?? undefined,
    };
  }

  const response = await fetch(`${BACKEND_URL}/api/papers/${paperId}/index`, {
    method: "POST",
    headers,
    body: JSON.stringify(bodyPayload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to index paper: ${errorText}`);
  }

  return response.json();
}

export async function uploadPaperPdf(paperId: string, file: File): Promise<RagIndexResponse> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${BACKEND_URL}/api/papers/${paperId}/upload-pdf`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to upload and index PDF: ${errorText}`);
  }

  return response.json();
}

export async function askPaperRAG(
  paperId: string,
  message: string,
  history: RagChatMessage[] = [],
  doi?: string | null,
  title?: string | null,
): Promise<RagChatResponse> {
  const headers = await getAuthHeader();
  const response = await fetch(`${BACKEND_URL}/api/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      paper_id: paperId,
      doi: doi ?? undefined,
      title: title ?? undefined,
      message,
      history,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`RAG Chat API error: ${errorText}`);
  }

  return response.json();
}

/**
 * Stream a RAG response via Server-Sent Events.
 * Returns an AbortController so the caller can cancel mid-stream.
 */
export async function streamPaperRAG(
  paperId: string,
  message: string,
  history: RagChatMessage[] = [],
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: Error) => void,
  doi?: string | null,
  title?: string | null,
): Promise<AbortController> {
  const headers = await getAuthHeader();
  const controller = new AbortController();

  fetch(`${BACKEND_URL}/api/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      paper_id: paperId,
      doi: doi ?? undefined,
      title: title ?? undefined,
      message,
      history,
    }),
    signal: controller.signal,
  })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body?.getReader();
      if (!reader) throw new Error("ReadableStream not supported");
      const decoder = new TextDecoder();
      let buffer = "";

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) {
            onDone();
            return;
          }
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.trim();
            if (line.startsWith("data:")) {
              const raw = line.slice(5).trim();
              if (raw) {
                try {
                  const parsed = JSON.parse(raw);
                  if (parsed.error) {
                    onError(new Error(parsed.error));
                    return;
                  }
                  if (typeof parsed.text === "string") {
                    onChunk(parsed.text);
                  } else if (typeof parsed.answer === "string") {
                    onChunk(parsed.answer);
                  }
                } catch {
                  // Ignore non-JSON or partial chunk buffers
                }
              }
            }
          }
          if (!controller.signal.aborted) read();
        }).catch((err) => {
          if (err.name === "AbortError") return;
          onError(err instanceof Error ? err : new Error(String(err)));
        });
      }

      read();
    })
    .catch((err) => {
      if (err.name === "AbortError") return;
      onError(err instanceof Error ? err : new Error(String(err)));
    });

  return controller;
}
