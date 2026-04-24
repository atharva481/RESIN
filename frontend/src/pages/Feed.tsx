import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTechNews, isNewsConfigured } from "@/lib/newsApi";
import { FeedCard } from "@/components/FeedCard";
import { PageHeader } from "@/components/PageHeader";
import { ConfigBanner } from "@/components/ConfigBanner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Loader2, Newspaper } from "lucide-react";

const TOPICS = ["LLMs", "AI Safety", "Robotics", "Biotech", "Quantum", "Climate", "Chips", "CRISPR"];

export default function Feed() {
  const [topic, setTopic] = useState<string>("LLMs");
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("LLMs");

  useEffect(() => { setSubmitted(query.trim() || topic); }, [topic]); // eslint-disable-line

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["news", submitted],
    queryFn: () => fetchTechNews(submitted, [submitted]),
    enabled: isNewsConfigured,
    staleTime: 1000 * 60 * 10,
  });

  const items = useMemo(() => data ?? [], [data]);

  return (
    <>
      <PageHeader
        eyebrow="Daily feed"
        title="What's new in tech & research today"
        description="Curated news and pre-prints, with optional AI-generated 2-line digests. Filter by topic or search a keyword."
      />

      <ConfigBanner />

      <div className="mb-6 flex flex-col gap-3 animate-fade-up">
        <form
          onSubmit={(e) => { e.preventDefault(); setSubmitted(query.trim() || topic); }}
          className="relative"
        >
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the feed — e.g. 'mixture of experts'"
            className="pl-10 h-11 bg-card border-border"
          />
        </form>
        <div className="flex flex-wrap gap-1.5">
          {TOPICS.map((t) => (
            <Button
              key={t}
              size="sm"
              variant={topic === t ? "default" : "outline"}
              onClick={() => { setTopic(t); setQuery(""); }}
              className={`h-7 text-xs rounded-full ${topic === t ? "" : "hover:bg-secondary"}`}
            >
              {t}
            </Button>
          ))}
        </div>
      </div>

      {!isNewsConfigured && (
        <EmptyState
          icon={Newspaper}
          title="Add your NewsAPI key to load the feed"
          desc="Get a free key at newsapi.org and add VITE_NEWS_API_KEY to your .env file."
        />
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Fetching latest stories…
        </div>
      )}
      {isError && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
          Couldn't load news: {(error as Error).message}
        </div>
      )}

      <div className="grid gap-4">
        {items.map((it) => <FeedCard key={it.id} item={it} />)}
      </div>

      {isNewsConfigured && !isLoading && items.length === 0 && (
        <EmptyState icon={Newspaper} title="No stories found" desc="Try a different topic or search term." />
      )}
    </>
  );
}

function EmptyState({ icon: Icon, title, desc }: { icon: React.ComponentType<{ className?: string }>; title: string; desc: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-12 text-center">
      <Icon className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
      <div className="font-serif-display text-lg font-semibold mb-1">{title}</div>
      <p className="text-sm text-muted-foreground">{desc}</p>
    </div>
  );
}
