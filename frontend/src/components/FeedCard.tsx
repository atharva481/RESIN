import { useState } from "react";
import { Calendar, ExternalLink, Sparkles, Loader2 } from "lucide-react";
import type { FeedItem } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { summariseArticle, isGeminiConfigured } from "@/lib/gemini";

interface FeedCardProps {
  item: FeedItem;
}

const readTime = (text?: string | null) => {
  const w = (text ?? "").split(/\s+/).length;
  return Math.max(1, Math.round(w / 200));
};

export function FeedCard({ item }: FeedCardProps) {
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAi = async () => {
    if (!isGeminiConfigured) return;
    setLoading(true);
    try {
      const s = await summariseArticle(item.title, item.summary);
      setAiSummary(s);
    } finally {
      setLoading(false);
    }
  };

  return (
    <article className="group flex gap-4 sm:gap-5 p-4 sm:p-5 rounded-xl border border-border bg-card hover:shadow-lift hover:border-foreground/20 transition-smooth animate-fade-up">
      {item.image_url && (
        <div className="hidden sm:block w-32 h-32 shrink-0 overflow-hidden rounded-lg bg-secondary">
          <img
            src={item.image_url}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover group-hover:scale-105 transition-smooth"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground mb-2">
          <span className="font-medium uppercase tracking-wider text-foreground">{item.source}</span>
          <span>·</span>
          {item.published_at && (
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {new Date(item.published_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </span>
          )}
          <span>·</span>
          <span>{readTime(item.summary)} min read</span>
        </div>

        <h3 className="font-serif-display text-lg sm:text-xl font-semibold leading-snug text-balance mb-2">
          <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-primary transition-smooth inline-flex items-start gap-2">
            {item.title}
            <ExternalLink className="h-3.5 w-3.5 mt-1.5 opacity-40 shrink-0" />
          </a>
        </h3>

        {(aiSummary || item.summary) && (
          <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3">
            {aiSummary ?? item.summary}
          </p>
        )}

        <div className="mt-auto pt-3 flex items-center gap-2">
          {!aiSummary && isGeminiConfigured && (
            <Button onClick={handleAi} disabled={loading} size="sm" variant="ghost" className="h-7 gap-1.5 text-xs">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3 text-primary" />}
              {loading ? "Summarising..." : "AI digest"}
            </Button>
          )}
          {item.topics.map((t) => (
            <span key={t} className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-secondary text-muted-foreground">
              {t}
            </span>
          ))}
        </div>
      </div>
    </article>
  );
}
