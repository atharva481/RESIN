import { useState, useEffect, useMemo } from "react";
import { listFolders as getFolders, createFolder, deleteFolder } from "@/lib/db";
import { listUserPapers, removeUserPaper, updateUserPaper } from "@/lib/db";
import { isSupabaseConfigured } from "@/lib/supabase";

import { PageHeader } from "@/components/PageHeader";
import { ConfigBanner } from "@/components/ConfigBanner";
import { PaperCard } from "@/components/PaperCard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FolderPlus, FolderOpen, Trash2, Loader2, Download, FileText, BookOpen, Network, ArrowUpDown, CheckSquare, X } from "lucide-react";
import { toast } from "sonner";
import { toBibTeX, toAPA, toMLA, downloadText } from "@/lib/cite";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Link } from "react-router-dom";
import type { Folder, UserPaper, Paper } from "@/lib/types";

export type LibrarySortOption =
  | "date_desc"
  | "date_asc"
  | "citations_desc"
  | "year_desc"
  | "year_asc"
  | "title_asc";

export default function Library() {
  const [name, setName] = useState("");
  const [activeFolder, setActiveFolder] = useState<string | null>(null);

  // Folder State
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loadingFolders, setLoadingFolders] = useState(false);

  // Papers State
  const [papers, setPapers] = useState<(UserPaper & { paper: Paper })[]>([]);
  const [loadingPapers, setLoadingPapers] = useState(false);

  // Multi-select State
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Sort State (persisted per folder in localStorage)
  const [sortBy, setSortBy] = useState<LibrarySortOption>(() => {
    return (
      (localStorage.getItem(`resin_sort_${activeFolder ?? "all"}`) as LibrarySortOption) ||
      "date_desc"
    );
  });

  // Sync sort preference when active folder changes
  useEffect(() => {
    const saved = localStorage.getItem(`resin_sort_${activeFolder ?? "all"}`);
    if (saved) {
      setSortBy(saved as LibrarySortOption);
    } else {
      setSortBy("date_desc");
    }
    // Reset selection when switching folders
    setSelectMode(false);
    setSelectedIds(new Set());
  }, [activeFolder]);

  const handleSortChange = (newSort: LibrarySortOption) => {
    setSortBy(newSort);
    try {
      localStorage.setItem(`resin_sort_${activeFolder ?? "all"}`, newSort);
    } catch {
      // Storage unavailable or disabled
    }
  };

  // Client-side sorting (instantaneous < 200ms)
  const sortedPapers = useMemo(() => {
    const list = [...papers];
    list.sort((a, b) => {
      switch (sortBy) {
        case "date_desc": {
          const timeA = a.saved_at ? new Date(a.saved_at).getTime() : 0;
          const timeB = b.saved_at ? new Date(b.saved_at).getTime() : 0;
          return timeB - timeA;
        }
        case "date_asc": {
          const timeA = a.saved_at ? new Date(a.saved_at).getTime() : 0;
          const timeB = b.saved_at ? new Date(b.saved_at).getTime() : 0;
          return timeA - timeB;
        }
        case "citations_desc": {
          const countA = a.paper?.citation_count ?? 0;
          const countB = b.paper?.citation_count ?? 0;
          return countB - countA;
        }
        case "year_desc": {
          const yearA = a.paper?.year ?? 0;
          const yearB = b.paper?.year ?? 0;
          return yearB - yearA;
        }
        case "year_asc": {
          const yearA = a.paper?.year ?? 9999;
          const yearB = b.paper?.year ?? 9999;
          return yearA - yearB;
        }
        case "title_asc": {
          const titleA = a.paper?.title ?? "";
          const titleB = b.paper?.title ?? "";
          return titleA.localeCompare(titleB);
        }
        default:
          return 0;
      }
    });
    return list;
  }, [papers, sortBy]);

  // Load Folders
  const fetchFolders = async () => {
    if (!isSupabaseConfigured) return;
    setLoadingFolders(true);
    try {
      const data = await getFolders();
      setFolders(data);
    } catch (e) {
      toast.error("Failed to load folders");
    } finally {
      setLoadingFolders(false);
    }
  };

  useEffect(() => {
    fetchFolders();
  }, []);

  // Load Papers
  const fetchPapers = async () => {
    if (!isSupabaseConfigured) return;
    setLoadingPapers(true);
    try {
      const data = await listUserPapers(activeFolder ?? undefined);
      setPapers(data);
    } catch (e) {
      toast.error("Failed to load papers");
    } finally {
      setLoadingPapers(false);
    }
  };

  useEffect(() => {
    fetchPapers();
  }, [activeFolder]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    try {
      await createFolder(name.trim());
      setName("");
      toast.success("Folder created");
      fetchFolders();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    }
  };

  const handleDeleteFolder = async (id: string) => {
    if (!confirm("Delete this folder and remove its saved papers?")) return;
    try {
      await deleteFolder(id);
      if (activeFolder === id) setActiveFolder(null);
      toast.success("Folder deleted");
      fetchFolders();
      fetchPapers(); // refresh papers in case we deleted the active folder
    } catch (e) {
      toast.error("Failed to delete folder");
    }
  };

  // ── Selection helpers ────────────────────────────────────────────────────
  const allIds = useMemo(() => sortedPapers.map((up) => up.paper.id), [sortedPapers]);
  const allSelected = allIds.length > 0 && allIds.every((id) => selectedIds.has(id));
  const someSelected = selectedIds.size > 0;

  const toggleSelectMode = () => {
    setSelectMode((v) => !v);
    setSelectedIds(new Set());
  };

  const togglePaper = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(allIds));
  const clearAll = () => setSelectedIds(new Set());

  // ── Export helpers ────────────────────────────────────────────────────────
  const getExportItems = (scope: "all" | "selected"): Paper[] => {
    if (scope === "selected") {
      return sortedPapers
        .filter((up) => selectedIds.has(up.paper.id))
        .map((up) => up.paper);
    }
    return sortedPapers.map((up) => up.paper);
  };

  const handleExport = (fmt: "bib" | "apa" | "mla", scope: "all" | "selected" = "all") => {
    const items = getExportItems(scope);
    if (!items.length) {
      toast.error(scope === "selected" ? "No papers selected" : "Nothing to export yet");
      return;
    }
    const folderName = folders.find((f) => f.id === activeFolder)?.name ?? "library";
    const safe = folderName.replace(/[^a-z0-9]/gi, "-").toLowerCase();
    const suffix = scope === "selected" ? "-selected" : "";
    if (fmt === "bib") downloadText(`${safe}${suffix}.bib`, toBibTeX(items));
    if (fmt === "apa") downloadText(`${safe}${suffix}-apa.txt`, toAPA(items));
    if (fmt === "mla") downloadText(`${safe}${suffix}-mla.txt`, toMLA(items));
    toast.success(`Exported ${items.length} paper${items.length !== 1 ? "s" : ""}`);
  };

  return (
    <>
      <PageHeader
        eyebrow="Personal library"
        title="Folders & saved research"
        description="Organise papers into folders, track reading status, and export citations."
        actions={
          activeFolder && (
            <>
              <Button asChild variant="outline" size="sm" className="gap-2">
                <Link to={`/graph?folder=${activeFolder}`}><Network className="h-3.5 w-3.5" /> Open graph</Link>
              </Button>

              {/* Select mode toggle */}
              <Button
                size="sm"
                variant={selectMode ? "secondary" : "outline"}
                className="gap-2"
                onClick={toggleSelectMode}
              >
                {selectMode ? (
                  <><X className="h-3.5 w-3.5" /> Cancel</>
                ) : (
                  <><CheckSquare className="h-3.5 w-3.5" /> Select</>
                )}
              </Button>

              {/* Export dropdown */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" className="gap-2">
                    <Download className="h-3.5 w-3.5" /> Export
                    {selectMode && someSelected && (
                      <span className="ml-1 bg-primary-foreground/20 text-primary-foreground rounded-full text-[10px] font-mono px-1.5 py-0 leading-4">
                        {selectedIds.size}
                      </span>
                    )}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
                  <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                    Export all papers
                  </div>
                  <DropdownMenuItem onClick={() => handleExport("bib", "all")}>BibTeX (.bib)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport("apa", "all")}>APA (.txt)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport("mla", "all")}>MLA (.txt)</DropdownMenuItem>
                  {selectMode && (
                    <>
                      <DropdownMenuSeparator />
                      <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                        Export selected ({selectedIds.size})
                      </div>
                      <DropdownMenuItem
                        onClick={() => handleExport("bib", "selected")}
                        disabled={!someSelected}
                      >
                        BibTeX (.bib)
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => handleExport("apa", "selected")}
                        disabled={!someSelected}
                      >
                        APA (.txt)
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => handleExport("mla", "selected")}
                        disabled={!someSelected}
                      >
                        MLA (.txt)
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )
        }
      />
      <ConfigBanner />

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6">
        {/* Folders sidebar */}
        <aside className="space-y-2">
          <div className="rounded-lg border border-border bg-card p-3">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2 px-1">Folders</div>
            <div className="flex gap-1.5 mb-2">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                placeholder="New folder"
                className="h-8 text-sm"
              />
              <Button size="icon" variant="outline" className="h-8 w-8 shrink-0" onClick={handleCreate}>
                <FolderPlus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="space-y-0.5">
              <button
                onClick={() => setActiveFolder(null)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-smooth ${
                  activeFolder === null ? "bg-foreground text-background" : "hover:bg-secondary"
                }`}
              >
                <BookOpen className="h-3.5 w-3.5" /> All saved
              </button>
              
              {loadingFolders && (
                <div className="flex items-center justify-center p-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              )}
              
              {!loadingFolders && folders.map((f) => (
                <div key={f.id} className="group flex items-center gap-1">
                  <button
                    onClick={() => setActiveFolder(f.id)}
                    className={`flex-1 flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-smooth text-left ${
                      activeFolder === f.id ? "bg-foreground text-background" : "hover:bg-secondary"
                    }`}
                  >
                    <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{f.name}</span>
                  </button>
                  <button
                    onClick={() => handleDeleteFolder(f.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 hover:text-destructive transition-smooth"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
              {!loadingFolders && folders.length === 0 && (
                <div className="text-xs text-muted-foreground px-2 py-3 text-center">No folders yet.</div>
              )}
            </div>
          </div>
        </aside>

        {/* Papers list */}
        <section className="space-y-4">
          {/* Header toolbar with paper count and sort options */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-border">
            <div className="text-sm text-muted-foreground">
              {loadingPapers ? (
                "Loading papers…"
              ) : (
                <span>
                  Showing <strong className="text-foreground font-medium">{sortedPapers.length}</strong> {sortedPapers.length === 1 ? "paper" : "papers"}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 self-end sm:self-auto">
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <ArrowUpDown className="h-3.5 w-3.5" /> Sort:
              </span>
              <Select value={sortBy} onValueChange={(v) => handleSortChange(v as LibrarySortOption)}>
                <SelectTrigger className="h-8 text-xs w-[190px] bg-card">
                  <SelectValue placeholder="Sort papers" />
                </SelectTrigger>
                <SelectContent align="end">
                  <SelectItem value="date_desc">Date saved (newest)</SelectItem>
                  <SelectItem value="date_asc">Date saved (oldest)</SelectItem>
                  <SelectItem value="citations_desc">Citation count (highest)</SelectItem>
                  <SelectItem value="year_desc">Year (newest)</SelectItem>
                  <SelectItem value="year_asc">Year (oldest)</SelectItem>
                  <SelectItem value="title_asc">Title (A–Z)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Selection toolbar — only visible in select mode */}
          {selectMode && !loadingPapers && sortedPapers.length > 0 && (
            <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-secondary/60 border border-border text-sm">
              <Checkbox
                id="select-all"
                checked={allSelected}
                onCheckedChange={(checked) => (checked ? selectAll() : clearAll())}
                className="data-[state=checked]:bg-foreground data-[state=checked]:border-foreground"
              />
              <label htmlFor="select-all" className="cursor-pointer font-medium select-none">
                {allSelected ? "Deselect all" : "Select all"}
              </label>
              <span className="text-muted-foreground text-xs">
                {selectedIds.size} of {sortedPapers.length} selected
              </span>
              {someSelected && (
                <button
                  onClick={clearAll}
                  className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-smooth"
                >
                  Clear
                </button>
              )}
            </div>
          )}

          {loadingPapers && (
            <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading saved papers…
            </div>
          )}

          {!loadingPapers && sortedPapers.length === 0 && (
            <div className="rounded-xl border border-dashed border-border p-12 text-center">
              <FileText className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
              <div className="font-serif-display text-lg font-semibold mb-1">Nothing saved here yet</div>
              <p className="text-sm text-muted-foreground mb-4">Find papers in the Paper Hub and save them to a folder.</p>
              <Button asChild size="sm" variant="outline"><Link to="/papers">Browse papers</Link></Button>
            </div>
          )}

          <div className="grid gap-4">
            {sortedPapers.map((up) => (
              <div key={up.id} className="relative flex gap-3 items-start">
                {/* Checkbox column — only in select mode */}
                {selectMode && (
                  <div className="pt-4 shrink-0">
                    <Checkbox
                      checked={selectedIds.has(up.paper.id)}
                      onCheckedChange={() => togglePaper(up.paper.id)}
                      className="data-[state=checked]:bg-foreground data-[state=checked]:border-foreground"
                      aria-label={`Select ${up.paper.title}`}
                    />
                  </div>
                )}

                {/* Paper card — highlighted when selected */}
                <div
                  className={`flex-1 min-w-0 transition-all duration-150 rounded-xl ${
                    selectMode && selectedIds.has(up.paper.id)
                      ? "ring-2 ring-foreground/40 ring-offset-1 ring-offset-background"
                      : ""
                  }`}
                  onClick={() => selectMode && togglePaper(up.paper.id)}
                  style={{ cursor: selectMode ? "pointer" : undefined }}
                >
                  <PaperCard
                    paper={up.paper}
                    persistedId={up.paper.id}
                    statusBadge={
                      <StatusPill
                        value={up.status}
                        onChange={async (s) => {
                          await updateUserPaper(up.id, { status: s });
                          fetchPapers();
                        }}
                      />
                    }
                    actionExtra={
                      !selectMode ? (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            await removeUserPaper(up.id);
                            fetchPapers();
                            toast.success("Removed from library");
                          }}
                          className="h-8 w-8 inline-flex items-center justify-center rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-smooth"
                          title="Remove from library"
                          aria-label="Remove from library"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      ) : undefined
                    }
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}

function StatusPill({
  value,
  onChange,
}: {
  value: "unread" | "in_progress" | "done";
  onChange: (s: "unread" | "in_progress" | "done") => void;
}) {
  const next = value === "unread" ? "in_progress" : value === "in_progress" ? "done" : "unread";
  const colors = {
    unread: "bg-secondary text-muted-foreground hover:bg-secondary/80 border-border",
    in_progress: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30 hover:bg-amber-500/20",
    done: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20",
  } as const;
  const labels = {
    unread: "Unread",
    in_progress: "In Progress",
    done: "Done",
  };
  return (
    <button
      onClick={() => onChange(next)}
      className={`text-[10px] font-mono-tech uppercase tracking-wider px-2 py-0.5 rounded-full border transition-smooth font-medium inline-flex items-center gap-1.5 shrink-0 ${colors[value]}`}
      title="Click to advance reading status (Unread → In Progress → Done)"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          value === "done" ? "bg-emerald-500" : value === "in_progress" ? "bg-amber-500" : "bg-muted-foreground/60"
        }`}
      />
      {labels[value]}
    </button>
  );
}
