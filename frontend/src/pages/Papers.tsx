import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchPapers } from "@/lib/semanticScholar";
import { PaperCard } from "@/components/PaperCard";
import { PageHeader } from "@/components/PageHeader";
import { ConfigBanner } from "@/components/ConfigBanner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Loader2, BookOpen, FileX } from "lucide-react";

const SUGGESTIONS = [
  "transformer architecture",
  "CRISPR off-target",
  "graph neural networks",
  "diffusion models",
  "quantum error correction",
];

export default function Papers() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [openAccessOnly, setOpenAccessOnly] = useState(false);
  const [sortBy, setSortBy] = useState<"relevance" | "citations" | "year">("relevance");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["papers", submitted],
    queryFn: () => searchPapers(submitted, 25),
    enabled: submitted.length > 0,
    staleTime: 1000 * 60 * 30,
  });

  const filtered = (data ?? [])
    .filter((p) => (openAccessOnly ? Boolean(p.open_access_url) : true))
    .sort((a, b) => {
      if (sortBy === "citations") return (b.citation_count ?? 0) - (a.citation_count ?? 0);
      if (sortBy === "year") return (b.year ?? 0) - (a.year ?? 0);
      return 0;
    });

  return (
    <>
      <PageHeader
        eyebrow="Paper hub"
        title="Search 200M+ open papers"
        description="Powered by Semantic Scholar. Every paper can be summarised by AI into Problem · Method · Findings · Limitations · Significance."
      />
      <ConfigBanner />

      <form
        onSubmit={(e) => { e.preventDefault(); setSubmitted(query.trim()); }}
        className="relative mb-3 animate-fade-up"
      >
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by topic, author, or keyword…"
          className="pl-10 pr-24 h-12 text-base bg-card"
        />
        <Button type="submit" size="sm" className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9">
          Search
        </Button>
      </form>

      <div className="flex flex-wrap items-center gap-2 mb-6 text-xs">
        {!submitted && (
          <>
            <span className="text-muted-foreground">Try:</span>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => { setQuery(s); setSubmitted(s); }}
                className="px-2.5 py-1 rounded-full border border-border hover:bg-secondary transition-smooth"
              >
                {s}
              </button>
            ))}
          </>
        )}
        {submitted && (
          <>
            <Button size="sm" variant={openAccessOnly ? "default" : "outline"} onClick={() => setOpenAccessOnly((v) => !v)} className="h-7 text-xs">
              Open access only
            </Button>
            <div className="flex gap-1">
              {(["relevance", "citations", "year"] as const).map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant={sortBy === s ? "default" : "ghost"}
                  onClick={() => setSortBy(s)}
                  className="h-7 text-xs capitalize"
                >
                  {s}
                </Button>
              ))}
            </div>
            <span className="ml-auto text-muted-foreground">{filtered.length} results</span>
          </>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Searching Semantic Scholar…
        </div>
      )}
      {isError && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
          Search failed: {(error as Error).message}
        </div>
      )}

      <div className="grid gap-4">
        {filtered.map((p) => <PaperCard key={p.id} paper={p} />)}
      </div>

      {!submitted && (
        <div className="rounded-xl border border-dashed border-border p-12 text-center">
          <BookOpen className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
          <div className="font-serif-display text-lg font-semibold mb-1">Start a search</div>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            Search across millions of open papers. Save the ones you care about into folders, then visualise the connections.
          </p>
        </div>
      )}
      {submitted && !isLoading && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-border p-12 text-center">
          <FileX className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
          <div className="font-serif-display text-lg font-semibold mb-1">No papers found</div>
          <p className="text-sm text-muted-foreground">Try a broader query.</p>
        </div>
      )}
    </>
  );
}
