import { Quote, Calendar, Users, ExternalLink, MessageSquare } from "lucide-react";
import type { Paper } from "@/lib/types";
import { SaveToFolder } from "@/components/SaveToFolder";
import { AISummary } from "@/components/AISummary";
import { PaperChat } from "@/components/PaperChat";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { upsertPaper, getSummary } from "@/lib/db";
import { useEffect, useState } from "react";
import type { PaperSummary } from "@/lib/types";

interface PaperCardProps {
  paper: Paper;
  /** When persisted (e.g. from library), pass uuid to enable summary caching */
  persistedId?: string;
}

export function PaperCard({ paper, persistedId }: PaperCardProps) {
  const [saved, setSaved] = useState(false);
  const [summary, setSummary] = useState<PaperSummary | null>(null);

  useEffect(() => {
    if (persistedId) getSummary(persistedId).then(setSummary).catch(() => {});
  }, [persistedId]);

  // Ensure paper is upserted before generating a summary so we can persist
  const ensurePersisted = async (): Promise<string> => {
    if (persistedId) return persistedId;
    const stored = await upsertPaper(paper);
    return stored.id;
  };

  return (
    <article className="group rounded-xl border border-border bg-card p-5 sm:p-6 transition-smooth hover:shadow-lift hover:border-foreground/20 animate-fade-up">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {paper.year && (
            <span className="inline-flex items-center gap-1"><Calendar className="h-3 w-3" />{paper.year}</span>
          )}
          <span className="inline-flex items-center gap-1">
            <Quote className="h-3 w-3" />
            <span className="font-mono-tech">{paper.citation_count.toLocaleString()}</span> citations
          </span>
          {paper.arxiv_id && (
            <span className="font-mono-tech text-[10px] px-1.5 py-0.5 rounded bg-secondary border border-border">
              arXiv:{paper.arxiv_id}
            </span>
          )}
        </div>
        <SaveToFolder variant="icon" saved={saved} onSaved={() => setSaved(true)} paper={paper} summary={summary} />
      </div>

      <h3 className="font-serif-display text-xl sm:text-2xl font-semibold leading-snug mb-2 text-balance group-hover:text-primary transition-smooth">
        {paper.open_access_url ? (
          <a href={paper.open_access_url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-2">
            <span>{paper.title}</span>
            <ExternalLink className="h-3.5 w-3.5 mt-2 opacity-50 shrink-0" />
          </a>
        ) : (
          paper.title
        )}
      </h3>

      {paper.authors.length > 0 && (
        <div className="flex items-start gap-2 text-sm text-muted-foreground mb-3">
          <Users className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span className="line-clamp-1">{paper.authors.slice(0, 6).join(" · ")}{paper.authors.length > 6 && ` · +${paper.authors.length - 6} more`}</span>
        </div>
      )}

      {paper.abstract && (
        <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3 mb-4">{paper.abstract}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <AISummaryWrapper paper={paper} initial={summary} ensurePersisted={ensurePersisted} />
        
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8">
              <MessageSquare className="h-3.5 w-3.5 text-primary" />
              Ask AI (RAG Chat)
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl p-4 sm:p-6">
            <DialogHeader className="mb-2">
              <DialogTitle className="text-lg font-serif-display line-clamp-1">
                Chat with: {paper.title}
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Ask questions and retrieve insights grounded in this paper using AI.
              </DialogDescription>
            </DialogHeader>
            <PaperChat paper={paper} />
          </DialogContent>
        </Dialog>

        {paper.doi && (
          <a
            href={`https://doi.org/${paper.doi}`}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground transition-smooth font-mono-tech inline-flex items-center gap-1"
          >
            doi:{paper.doi.split("/").slice(-1)[0]} <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </article>
  );
}

/** Lazily resolves the persisted paper id when the user clicks "AI summary". */
function AISummaryWrapper({
  paper,
  initial,
  ensurePersisted,
}: {
  paper: Paper;
  initial: PaperSummary | null;
  ensurePersisted: () => Promise<string>;
}) {
  const [pid, setPid] = useState<string | undefined>(undefined);
  // Lazy: when AISummary mounts and Generate is clicked, we still need pid to persist.
  // Trigger ensurePersisted on first interaction by wrapping:
  useEffect(() => {
    let cancelled = false;
    ensurePersisted().then((id) => { if (!cancelled) setPid(id); }).catch(() => {});
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return <AISummary paper={paper} initial={initial} persistPaperId={pid} />;
}
