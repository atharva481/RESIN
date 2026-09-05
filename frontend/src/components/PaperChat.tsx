import ReactMarkdown from "react-markdown";
import { useState, useEffect, useRef, useCallback } from "react";
import { MessageSquare, Send, Loader2, Sparkles, BookOpen, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { askPaperRAG, indexPaper, streamPaperRAG } from "@/lib/ragApi";
import type { Paper, RagChatMessage } from "@/lib/types";
import { toast } from "sonner";

interface PaperChatProps {
  paper: Paper;
}

export function PaperChat({ paper }: PaperChatProps) {
  const [messages, setMessages] = useState<RagChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [isIndexed, setIsIndexed] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleIndexPaper = async () => {
    setIndexing(true);
    try {
      const res = await indexPaper(paper.id, paper.abstract || undefined);
      setIsIndexed(true);
      toast.success(res.message || "Paper indexed successfully for AI Chat.");
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
    setStreaming(true);

    try {
      // Auto-index if not already done
      if (!isIndexed) {
        await indexPaper(paper.id, paper.abstract || undefined);
        setIsIndexed(true);
      }

      await streamPaperRAG(
        paper.id,
        userMessage,
        newHistory,
        (chunk) => {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant") {
              return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
            }
            return [...prev, { role: "assistant", content: chunk, citations: [] }];
          });
        },
        () => {
          setStreaming(false);
          setLoading(false);
        },
        async (err) => {
          console.warn("Stream failed, falling back to non-streaming:", err);
          setStreaming(false);
          try {
            // Clear out any partial streaming message before calling fallback
            setMessages(newHistory);
            const response = await askPaperRAG(paper.id, userMessage, newHistory);
            setMessages([
              ...newHistory,
              { role: "assistant", content: response.answer, citations: response.citations },
            ]);
          } catch (fallbackErr) {
            toast.error(fallbackErr instanceof Error ? fallbackErr.message : "Failed to get answer from AI.");
          } finally {
            setLoading(false);
          }
        },
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to get answer from AI.");
      setStreaming(false);
      setLoading(false);
    }
  }, [input, loading, isIndexed, messages, paper.id]);

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
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={handleIndexPaper}
            disabled={indexing}
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

              {/* Citations Badges */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1 max-w-[85%]">
                  {msg.citations.map((cite, idx) => (
                    <span
                      key={idx}
                      title={`${cite.paper_title || ''}\nSnippet: ${cite.content_snippet}`}
                      className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-accent/30 text-accent-foreground border border-border"
                    >
                      <BookOpen className="h-2.5 w-2.5" />
                      {cite.paper_title ? `${cite.paper_title.slice(0, 20)}... | ` : ''}
                      {cite.page_number ? `p. ${cite.page_number} | ` : ''}
                      {cite.section_title || `Chunk #${cite.chunk_index}`}
                    </span>
                  ))}

                </div>
              )}
            </div>
          ))
        )}

        {loading && !streaming && (
          <div className="flex items-center gap-2 text-muted-foreground text-xs p-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            Searching paper chunks & generating answer...
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
