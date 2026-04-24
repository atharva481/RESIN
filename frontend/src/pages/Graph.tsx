import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MiniMap, type Edge, type Node, MarkerType } from "reactflow";
import "reactflow/dist/style.css";
import { useSearchParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listFolders, listUserPapers, listCitationEdges, computeAuthorEdges } from "@/lib/db";
import type { Paper, CitationEdge } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import { ConfigBanner } from "@/components/ConfigBanner";
import { Button } from "@/components/ui/button";
import { Network as NetworkIcon, Link2, Users, Sparkles } from "lucide-react";

const EDGE_STYLES: Record<CitationEdge["edge_type"], { color: string; dash?: string; label: string; icon: typeof Link2 }> = {
  direct_citation: { color: "hsl(var(--node-citation))", label: "Direct citation", icon: Link2 },
  shared_citation: { color: "hsl(var(--node-citation))", dash: "4 4", label: "Shared citation", icon: Link2 },
  same_author: { color: "hsl(var(--node-author))", dash: "6 4", label: "Same author", icon: Users },
  topic_similarity: { color: "hsl(var(--node-topic))", dash: "1 4", label: "Topic similarity", icon: Sparkles },
};

export default function Graph() {
  const [params] = useSearchParams();
  const initialFolder = params.get("folder");
  const [folderId, setFolderId] = useState<string | null>(initialFolder);
  const [filters, setFilters] = useState<Record<CitationEdge["edge_type"], boolean>>({
    direct_citation: true,
    shared_citation: true,
    same_author: true,
    topic_similarity: true,
  });

  const foldersQ = useQuery({ queryKey: ["folders"], queryFn: listFolders });
  const libraryQ = useQuery({
    queryKey: ["library", folderId],
    queryFn: () => listUserPapers(folderId ?? undefined),
  });

  const papers: Paper[] = useMemo(() => (libraryQ.data ?? []).map((u) => u.paper), [libraryQ.data]);

  const dbEdgesQ = useQuery({
    queryKey: ["edges", papers.map((p) => p.id).join(",")],
    queryFn: () => listCitationEdges(papers.map((p) => p.id)),
    enabled: papers.length > 0,
  });

  const edges = useMemo<CitationEdge[]>(() => {
    const author = computeAuthorEdges(papers);
    const all = [...(dbEdgesQ.data ?? []), ...author];
    return all.filter((e) => filters[e.edge_type]);
  }, [papers, dbEdgesQ.data, filters]);

  // Build React Flow nodes in a circle layout
  const nodes: Node[] = useMemo(() => {
    const n = papers.length;
    if (n === 0) return [];
    const radius = Math.max(180, n * 35);
    const maxCit = Math.max(1, ...papers.map((p) => p.citation_count));
    return papers.map((p, i) => {
      const angle = (i / n) * Math.PI * 2;
      const sizeScale = 0.6 + 0.6 * (Math.log10(p.citation_count + 1) / Math.log10(maxCit + 1));
      const size = 60 + 80 * sizeScale;
      return {
        id: p.id,
        position: { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius },
        data: { label: p.title.length > 50 ? p.title.slice(0, 50) + "…" : p.title },
        style: {
          width: size,
          height: size,
          borderRadius: "50%",
          background: "hsl(var(--card))",
          border: `2px solid hsl(var(--primary))`,
          color: "hsl(var(--foreground))",
          fontSize: 10,
          fontFamily: "Fraunces, Georgia, serif",
          padding: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          boxShadow: "var(--shadow-paper)",
        },
      } as Node;
    });
  }, [papers]);

  const flowEdges: Edge[] = useMemo(() => {
    return edges.map((e, i) => {
      const s = EDGE_STYLES[e.edge_type];
      return {
        id: `${e.paper_id_a}-${e.paper_id_b}-${e.edge_type}-${i}`,
        source: e.paper_id_a,
        target: e.paper_id_b,
        animated: e.edge_type === "direct_citation",
        style: { stroke: s.color, strokeWidth: 1.5, strokeDasharray: s.dash },
        markerEnd: e.edge_type === "direct_citation" ? { type: MarkerType.ArrowClosed, color: s.color } : undefined,
      };
    });
  }, [edges]);

  useEffect(() => { if (initialFolder) setFolderId(initialFolder); }, [initialFolder]);

  return (
    <>
      <PageHeader
        eyebrow="Connection graph"
        title="How your saved papers connect"
        description="Each node is a paper. Size scales with citation count. Edges show shared authors, citations, and topical similarity."
      />
      <ConfigBanner />

      <div className="flex flex-wrap gap-2 mb-4 items-center animate-fade-up">
        <span className="text-xs uppercase tracking-wider text-muted-foreground mr-2">Folder:</span>
        <Button size="sm" variant={folderId === null ? "default" : "outline"} onClick={() => setFolderId(null)} className="h-7 text-xs">
          All saved
        </Button>
        {foldersQ.data?.map((f) => (
          <Button
            key={f.id}
            size="sm"
            variant={folderId === f.id ? "default" : "outline"}
            onClick={() => setFolderId(f.id)}
            className="h-7 text-xs"
          >
            {f.name}
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {(Object.keys(EDGE_STYLES) as CitationEdge["edge_type"][]).map((k) => {
          const s = EDGE_STYLES[k];
          const Icon = s.icon;
          return (
            <button
              key={k}
              onClick={() => setFilters((f) => ({ ...f, [k]: !f[k] }))}
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-smooth ${
                filters[k] ? "bg-secondary border-foreground/20" : "bg-background border-border opacity-50"
              }`}
            >
              <span className="inline-block w-3 h-0.5" style={{ background: s.color, borderTop: s.dash ? `1px dashed ${s.color}` : undefined }} />
              <Icon className="h-3 w-3" />
              {s.label}
            </button>
          );
        })}
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden" style={{ height: 560 }}>
        {papers.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-6">
            <NetworkIcon className="h-10 w-10 text-muted-foreground mb-3" />
            <div className="font-serif-display text-lg font-semibold mb-1">No saved papers to graph yet</div>
            <p className="text-sm text-muted-foreground mb-4">Save at least 2 papers to a folder to see connections.</p>
            <Button asChild size="sm" variant="outline"><Link to="/papers">Find papers</Link></Button>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={flowEdges}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1} color="hsl(var(--border))" />
            <Controls className="!bg-card !border-border" />
            <MiniMap pannable zoomable className="!bg-secondary" nodeColor="hsl(var(--primary))" />
          </ReactFlow>
        )}
      </div>

      <div className="mt-3 text-xs text-muted-foreground">
        {papers.length} papers · {edges.length} edges shown
      </div>
    </>
  );
}
