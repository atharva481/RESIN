import { useState } from "react";
import { Loader2, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { generatePaperSummary, isGeminiConfigured } from "@/lib/gemini";
import { saveSummary } from "@/lib/db";
import type { Paper, PaperSummary } from "@/lib/types";
import { toast } from "sonner";

interface AISummaryProps {
  paper: Paper;
  /** Existing summary loaded from DB, if any */
  initial?: PaperSummary | null;
  /** Pass paper id from DB (uuid) so we can persist; if not provided, summary is in-memory only */
  persistPaperId?: string;
}

const sections: { key: keyof Omit<PaperSummary, "paper_id" | "generated_at">; label: string; tone: string }[] = [
  { key: "problem", label: "Problem", tone: "text-foreground" },
  { key: "method", label: "Method", tone: "text-foreground" },
  { key: "findings", label: "Findings", tone: "text-foreground" },
  { key: "limitations", label: "Limitations", tone: "text-muted-foreground" },
  { key: "significance", label: "Why it matters", tone: "text-primary" },
];

export function AISummary({ paper, initial, persistPaperId }: AISummaryProps) {
  const [summary, setSummary] = useState<PaperSummary | null>(initial ?? null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(Boolean(initial));

  const handleGenerate = async () => {
    if (!isGeminiConfigured) {
      toast.error("Add VITE_GEMINI_API_KEY to .env to generate summaries");
      return;
    }
    setLoading(true);
    try {
      const out = await generatePaperSummary({
        title: paper.title,
        abstract: paper.abstract,
        authors: paper.authors,
        year: paper.year,
      });
      const next: PaperSummary = { paper_id: persistPaperId ?? paper.id, ...out };
      setSummary(next);
      setOpen(true);
      if (persistPaperId) {
        try { await saveSummary(next); } catch { /* non-fatal */ }
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to generate summary");
    } finally {
      setLoading(false);
    }
  };

  if (!summary) {
    return (
      <Button onClick={handleGenerate} disabled={loading} size="sm" variant="outline" className="gap-2">
        {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        {loading ? "Reading paper..." : "AI summary"}
      </Button>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden animate-fade-up">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-secondary/40 hover:bg-secondary transition-smooth"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          AI structured digest
        </span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="p-4 space-y-3">
          {sections.map((s) => {
            const v = summary[s.key];
            if (!v) return null;
            return (
              <div key={s.key} className="grid grid-cols-[110px_1fr] gap-3 text-sm">
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium pt-0.5">
                  {s.label}
                </div>
                <div className={`leading-relaxed ${s.tone}`}>{v}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
