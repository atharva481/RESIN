import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import type { Folder, Paper, PaperSummary, UserPaper, CitationEdge } from "@/lib/types";

/** All DB calls return null/[] if Supabase isn't configured, so the UI degrades gracefully. */

async function getUserId(): Promise<string | null> {
  if (!supabase) return null;
  const { data: { user } } = await supabase.auth.getUser();
  return user?.id ?? null;
}

export async function listFolders(): Promise<Folder[]> {
  const uid = await getUserId();
  if (!uid || !supabase) return [];
  const { data, error } = await supabase
    .from("folders")
    .select("*")
    .eq("user_id", uid)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

export async function createFolder(name: string): Promise<Folder> {
  const uid = await getUserId();
  if (!uid || !supabase) throw new Error("Not authenticated");
  
  const { data, error } = await supabase
    .from("folders")
    .insert({ name, user_id: uid })
    .select()
    .single();
  if (error) throw error;
  return data as Folder;
}

export async function deleteFolder(id: string): Promise<void> {
  if (!supabase) return;
  await supabase.from("user_papers").delete().eq("folder_id", id);
  const { error } = await supabase.from("folders").delete().eq("id", id);
  if (error) throw error;
}

/** Upsert a paper by semantic_scholar_id and return the canonical row (with uuid). */
export async function upsertPaper(p: Paper): Promise<Paper> {
  if (!supabase) throw new Error("Supabase not configured");
  const payload = {
    doi: p.doi,
    title: p.title,
    authors: p.authors,
    year: p.year,
    abstract: p.abstract,
    citation_count: p.citation_count,
    open_access_url: p.open_access_url,
    semantic_scholar_id: p.semantic_scholar_id,
    arxiv_id: p.arxiv_id,
  };
  // Try by semantic_scholar_id first
  if (p.semantic_scholar_id) {
    const { data: existing } = await supabase
      .from("papers")
      .select("*")
      .eq("semantic_scholar_id", p.semantic_scholar_id)
      .maybeSingle();
    if (existing) return existing as Paper;
  }
  const { data, error } = await supabase.from("papers").insert(payload).select().single();
  if (error) throw error;
  return data as Paper;
}

export async function savePaperToFolder(paper: Paper, folderId: string): Promise<void> {
  const uid = await getUserId();
  if (!uid || !supabase) throw new Error("Not authenticated");
  
  const stored = await upsertPaper(paper);
  const { error } = await supabase.from("user_papers").insert({
    user_id: uid,
    paper_id: stored.id,
    folder_id: folderId,
    status: "unread",
  });
  if (error && !error.message.includes("duplicate")) throw error;
}

export async function listUserPapers(folderId?: string): Promise<(UserPaper & { paper: Paper })[]> {
  const uid = await getUserId();
  if (!uid || !supabase) return [];
  let q = supabase
    .from("user_papers")
    .select("*, paper:papers(*)")
    .eq("user_id", uid)
    .order("saved_at", { ascending: false });
  if (folderId) q = q.eq("folder_id", folderId);
  const { data, error } = await q;
  if (error) throw error;
  return (data ?? []) as (UserPaper & { paper: Paper })[];
}

export async function updateUserPaper(id: string, patch: Partial<UserPaper>): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase.from("user_papers").update(patch).eq("id", id);
  if (error) throw error;
}

export async function removeUserPaper(id: string): Promise<void> {
  if (!supabase) return;
  await supabase.from("user_papers").delete().eq("id", id);
}

export async function getSummary(paperId: string): Promise<PaperSummary | null> {
  if (!supabase) return null;
  const { data } = await supabase.from("paper_summaries").select("*").eq("paper_id", paperId).maybeSingle();
  return (data as PaperSummary) ?? null;
}

export async function saveSummary(s: PaperSummary): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase.from("paper_summaries").upsert(s, { onConflict: "paper_id" });
  if (error) throw error;
}

export async function listCitationEdges(paperIds: string[]): Promise<CitationEdge[]> {
  if (!supabase || paperIds.length === 0) return [];
  const { data, error } = await supabase
    .from("citation_edges")
    .select("*")
    .or(`paper_id_a.in.(${paperIds.join(",")}),paper_id_b.in.(${paperIds.join(",")})`);
  if (error) throw error;
  return (data ?? []).filter(
    (e: CitationEdge) => paperIds.includes(e.paper_id_a) && paperIds.includes(e.paper_id_b),
  );
}

/** Compute "same_author" edges client-side from the paper list. */
export function computeAuthorEdges(papers: Paper[]): CitationEdge[] {
  const edges: CitationEdge[] = [];
  for (let i = 0; i < papers.length; i++) {
    for (let j = i + 1; j < papers.length; j++) {
      const a = new Set(papers[i].authors.map((x) => x.toLowerCase()));
      const shared = papers[j].authors.filter((x) => a.has(x.toLowerCase()));
      if (shared.length > 0) {
        edges.push({
          paper_id_a: papers[i].id,
          paper_id_b: papers[j].id,
          edge_type: "same_author",
          weight: shared.length,
        });
      }
    }
  }
  return edges;
}

export { isSupabaseConfigured };
