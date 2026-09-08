import { useQuery } from "@tanstack/react-query";
import { getDailyTriage } from "@/lib/supabase";
import { ExternalLink, Loader2, Sparkles, Bot } from "lucide-react";
import type { TriageItem } from "@/lib/types";

const RANK_LABELS = ["#1 Pick", "#2 Pick", "#3 Pick"];
const RANK_COLORS = [
  "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400",
  "bg-sky-500/15 border-sky-500/40 text-sky-600 dark:text-sky-400",
  "bg-violet-500/15 border-violet-500/40 text-violet-600 dark:text-violet-400",
];

function SourceBadge({ source }: { source: string }) {
  const label =
    source === "openalex"
      ? "OpenAlex"
      : source === "feed_item"
      ? "Feed"
      : source.charAt(0).toUpperCase() + source.slice(1);
  return (
    <span className="inline-block px-2 py-0.5 text-[10px] font-mono-tech tracking-wide rounded-full border border-border bg-secondary text-muted-foreground uppercase">
      {label}
    </span>
  );
}

function TriageCard({ item, rank }: { item: TriageItem; rank: number }) {
  return (
    <article
      className="group relative rounded-xl border border-border bg-card hover:border-foreground/20 hover:shadow-lift transition-smooth p-5 flex flex-col gap-3 animate-fade-up"
      style={{ animationDelay: `${rank * 60}ms` }}
    >
      {/* Rank badge */}
      <div className="flex items-center justify-between gap-3">
        <span
          className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${RANK_COLORS[rank]}`}
        >
          <Sparkles className="h-3 w-3" />
          {RANK_LABELS[rank]}
        </span>
        <SourceBadge source={item.source} />
      </div>

      {/* Title */}
      <h3 className="font-serif-display text-base sm:text-lg font-semibold leading-snug text-balance group-hover:text-primary transition-smooth">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-start gap-1.5"
          >
            <span>{item.title}</span>
            <ExternalLink className="h-3.5 w-3.5 mt-1 opacity-50 shrink-0" />
          </a>
        ) : (
          item.title
        )}
      </h3>

      {/* AI reason */}
      {item.reason && (
        <div className="flex items-start gap-2 text-xs text-muted-foreground bg-secondary/60 rounded-lg px-3 py-2 border border-border/50">
          <Bot className="h-3.5 w-3.5 mt-0.5 shrink-0 text-primary/70" />
          <span className="leading-relaxed">{item.reason}</span>
        </div>
      )}
    </article>
  );
}

export function DailyTriageSection() {
  const { data: triage, isLoading } = useQuery({
    queryKey: ["daily-triage"],
    queryFn: getDailyTriage,
    staleTime: 1000 * 60 * 30, // 30 min — results don't change mid-day
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Loading today's top picks…
      </div>
    );
  }

  if (!triage || !triage.items || triage.items.length === 0) {
    return null; // No triage for today — section simply doesn't show
  }

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  return (
    <section className="mb-8 animate-fade-up">
      {/* Header */}
      <div className="flex items-center gap-2.5 mb-4">
        <div className="h-8 w-8 rounded-lg bg-gradient-ink flex items-center justify-center shadow-ink shrink-0">
          <Sparkles className="h-4 w-4 text-paper" />
        </div>
        <div>
          <h2 className="font-serif-display text-lg font-bold leading-tight">
            Today's Top Reads
          </h2>
          <p className="text-xs text-muted-foreground">{today} · AI-curated for your library</p>
        </div>
      </div>

      {/* Cards grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {triage.items.slice(0, 3).map((item, i) => (
          <TriageCard key={item.id} item={item} rank={i} />
        ))}
      </div>

      {/* Divider */}
      <div className="mt-8 flex items-center gap-3">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">Search all papers</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    </section>
  );
}
