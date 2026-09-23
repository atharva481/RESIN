import ReactMarkdown from "react-markdown";
import { useState, useEffect, useRef, useCallback } from "react";
import { MessageSquare, Send, Loader2, Sparkles, Database, Upload, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { askPaperRAG, checkPaperIndexStatus, indexPaper, streamPaperRAG, uploadPaperPdf } from "@/lib/ragApi";
import type { Paper, RagChatMessage } from "@/lib/types";
import { toast } from "sonner";

interface PaperChatProps {
  paper: Paper;
}

export function PaperChat({ paper }: PaperChatProps) {
  const [canonicalId, setCanonicalId] = useState<string>(paper.id);
  const [messages, setMessages] = useState<RagChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState<string | null>(null);
  const [indexing, setIndexing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [indexNotice, setIndexNotice] = useState<string | null>(null);
  const [isIndexed, setIsIndexed] = useState(Boolean((paper as any).indexed_at));
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let mounted = true;
    checkPaperIndexStatus(paper.id)
      .then((res) => {
        if (!mounted) return;
        if (res.canonical_paper_id) {
          setCanonicalId(res.canonical_paper_id);
        }
        if (res.is_fully_indexed) {
          setIsIndexed(true);
          setIndexNotice(null);
        } else if (res.is_partial) {
          setIsIndexed(false);
          setIndexNotice(`Incomplete index detected (${res.chunk_count} chunk${res.chunk_count > 1 ? 's' : ''}). Will automatically re-index full paper on first question.`);
        } else {
          setIsIndexed(false);
        }
      })
      .catch(() => {
        if (mounted && (paper as any).indexed_at) {
          setIsIndexed(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, [paper.id]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadPaperPdf(canonicalId || paper.id, file);
      if (res.canonical_paper_id) {
        setCanonicalId(res.canonical_paper_id);
      }
      setIsIndexed(true);
      setIndexNotice(null);
      toast.success(res.message || "Full PDF successfully uploaded & indexed!");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to upload PDF.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleIndexPaper = async () => {
    setIndexing(true);
    try {
      // Force re-index if button is clicked explicitly
      const res = await indexPaper(paper.id, {
        abstract: paper.abstract || undefined,
        force: true,
        title: paper.title,
        doi: paper.doi,
        arxivId: paper.arxiv_id,
        openAccessUrl: paper.open_access_url,
      });
      if (res.canonical_paper_id) {
        setCanonicalId(res.canonical_paper_id);
      }
      if (res.status === "error" || (res.chunks_created === 0 && res.failure_reason === "EMBEDDING_QUOTA_EXCEEDED")) {
        setIsIndexed(false);
        setIndexNotice(res.message);
        toast.error(res.message);
      } else if (res.status === "warning" || res.chunks_created <= 1) {
        setIsIndexed(res.chunks_created > 0);
        setIndexNotice(res.message);
        toast.warning(res.message);
      } else {
        setIsIndexed(true);
        setIndexNotice(null);
        toast.success(res.message || "Paper indexed successfully for AI Chat.");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to index paper for RAG.");
    } finally {
      setIndexing(false);
    }
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");

    const newHistory: RagChatMessage[] = [
      ...messages,
      { role: "user", content: userMessage },
    ];
    setMessages(newHistory);
    setLoading(true);
    setStreaming(false);
    setLoadingStatus("Verifying paper indexing...");

    try {
      let activeTargetId = canonicalId || paper.id;

      // Auto-index if not already done (fast check via backend; will not re-download if chunks exist)
      if (!isIndexed) {
        setLoadingStatus("Fetching & indexing paper from source (discovering PDF, extracting pages)...");
        const indexRes = await indexPaper(paper.id, {
          abstract: paper.abstract || undefined,
          force: false,
          title: paper.title,
          doi: paper.doi,
          arxivId: paper.arxiv_id,
          openAccessUrl: paper.open_access_url,
        });
        if (indexRes.canonical_paper_id) {
          activeTargetId = indexRes.canonical_paper_id;
          setCanonicalId(indexRes.canonical_paper_id);
        }

        // If indexing failed or produced 0 chunks (e.g. EMBEDDING_QUOTA_EXCEEDED or no PDF found)
        if (indexRes.status === "error" || indexRes.chunks_created === 0) {
          setIsIndexed(false);
          setLoading(false);
          setStreaming(false);
          setLoadingStatus(null);
          const errText = indexRes.message || "Failed to index paper content.";
          if (indexRes.failure_reason === "EMBEDDING_QUOTA_EXCEEDED") {
            toast.error(errText);
          } else {
            toast.warning(errText);
          }
          setIndexNotice(errText);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: `⚠️ **Indexing Notice:** ${errText}` },
          ]);
          return;
        }

        setIsIndexed(true);
        if (indexRes.is_reindex) {
          toast.info(indexRes.message || "Recovered from incomplete index and re-indexed full paper.");
        }
      }

      setLoadingStatus("Searching paper chunks & generating answer...");
      const response = await askPaperRAG(
        activeTargetId,
        userMessage,
        newHistory,
        paper.doi,
        paper.title,
      );
      setMessages([
        ...newHistory,
        { role: "assistant", content: response.answer, citations: response.citations },
      ]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to get answer from AI.");
    } finally {
      setLoading(false);
      setStreaming(false);
      setLoadingStatus(null);
    }
  }, [input, loading, isIndexed, messages, canonicalId, paper.id, paper.doi, paper.title]);

  return (
    <div className="flex flex-col h-[500px] border border-border rounded-xl bg-card overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-secondary/30 border-b border-border">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">Interactive Paper Q&A</span>
          {streaming && (
            <span className="text-[10px] text-primary animate-pulse">Streaming</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <input
            type="file"
            ref={fileInputRef}
            accept="application/pdf"
            className="hidden"
            onChange={handleFileUpload}
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || indexing}
            className="text-xs h-7 gap-1 text-primary border-primary/30 hover:bg-primary/10"
            title="Upload full PDF for paywalled or custom papers"
          >
            {uploading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Upload className="h-3 w-3" />
            )}
            Upload PDF
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={handleIndexPaper}
            disabled={indexing || uploading}
            className="text-xs h-7 gap-1"
          >
            {indexing ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Database className="h-3 w-3 text-muted-foreground" />
            )}
            {isIndexed ? "Re-index" : "Index Paper"}
          </Button>
        </div>
      </div>

      {/* Paywall / Abstract Fallback Notice */}
      {indexNotice && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-3.5 py-2 text-xs text-amber-600 dark:text-amber-400 flex items-center justify-between gap-2 animate-fade-in">
          <div className="flex items-center gap-1.5 min-w-0">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
            <span className="truncate">{indexNotice}</span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            className="h-5 text-[11px] px-2 text-primary font-semibold underline underline-offset-2 shrink-0 hover:bg-transparent"
          >
            Upload PDF
          </Button>
        </div>
      )}

      {/* Messages Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground space-y-2 p-6">
            <Sparkles className="h-8 w-8 text-primary/60 animate-pulse" />
            <p className="font-medium text-foreground">Ask anything about this research paper</p>
            <p className="text-xs max-w-xs">
              Powered by section-aware RAG vector search & Gemini LLM. Ask about methods, datasets, findings, or code!
            </p>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex flex-col space-y-1 ${
                msg.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 leading-relaxed ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground font-medium"
                    : "bg-secondary/60 text-foreground border border-border"
                }`}
              >
                {msg.role === "assistant" ? (
                  <div className="prose dark:prose-invert max-w-none text-sm leading-relaxed space-y-2">
                    <ReactMarkdown>
                      {msg.content || ""}
                    </ReactMarkdown>
                  </div>
                ) : (
                  msg.content
                )}
              </div>
            </div>
          ))
        )}

        {loading && !streaming && (
          <div className="flex items-center gap-2 text-muted-foreground text-xs p-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            <span>{loadingStatus || "Searching paper chunks & generating answer..."}</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="p-3 bg-background border-t border-border flex items-center gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ask a question about this paper..."
          disabled={loading}
          className="flex-1 text-sm bg-card"
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="gap-1 px-3"
        >
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
