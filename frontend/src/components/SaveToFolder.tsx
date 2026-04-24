import { useEffect, useState } from "react";
import { Bookmark, Check, FolderPlus, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { getFolders, createFolder, savePaperToFolder, savePaperSummary } from "@/lib/supabase";
import type { Folder, Paper, PaperSummary } from "@/lib/types";
import { toast } from "sonner";

interface SaveToFolderProps {
  paper: Paper;
  summary?: PaperSummary | null;
  variant?: "icon" | "button";
  saved?: boolean;
  onSaved?: () => void;
}

export function SaveToFolder({ paper, summary, variant = "button", saved, onSaved }: SaveToFolderProps) {
  const [open, setOpen] = useState(false);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) getFolders().then(setFolders).catch(() => setFolders([]));
  }, [open]);

  const handleSave = async (id: string) => {
    setLoading(true);
    try {
      const paperId = await savePaperToFolder(paper, id);
      if (summary) {
        await savePaperSummary(paperId, summary);
      }
      toast.success("Saved to folder");
      if (onSaved) onSaved();
      setOpen(false);
    } catch (e: any) {
      toast.error(e.message || "Failed to save");
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!name.trim()) return;
    setLoading(true);
    try {
      const f = await createFolder(name.trim());
      setFolders((prev) => [f, ...prev]);
      setName("");
      await handleSave(f.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
      setLoading(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {variant === "icon" ? (
          <Button size="icon" variant="ghost" className="h-8 w-8 hover:bg-secondary">
            {saved ? <Check className="h-4 w-4 text-primary" /> : <Bookmark className="h-4 w-4" />}
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="gap-2">
            {saved ? <Check className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
            {saved ? "Saved" : "Save"}
          </Button>
        )}
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0 overflow-hidden" align="end">
        <div className="px-3 py-2 border-b border-border bg-secondary/40">
          <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Save to folder</div>
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {folders.length === 0 && (
            <div className="px-3 py-4 text-xs text-muted-foreground text-center">No folders yet — create one below.</div>
          )}
          {folders.map((f) => (
            <button
              key={f.id}
              onClick={() => handleSave(f.id)}
              disabled={loading}
              className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-secondary transition-smooth disabled:opacity-50"
            >
              <span className="truncate">{f.name}</span>
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            </button>
          ))}
        </div>
        <div className="border-t border-border p-2 flex gap-1.5">
          <Input
            placeholder="New folder name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            className="h-8 text-sm"
          />
          <Button size="icon" variant="outline" className="h-8 w-8 shrink-0" onClick={handleCreate} disabled={loading}>
            <FolderPlus className="h-3.5 w-3.5" />
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
