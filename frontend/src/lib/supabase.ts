/**
 * Supabase client. Reads keys from Vite env vars.
 * To wire your own Supabase project, create a `.env` file at project root with:
 *   VITE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
 *   VITE_SUPABASE_ANON_KEY=eyJhbGciOi...
 *   VITE_NEWS_API_KEY=...           (newsapi.org)
 *   VITE_GEMINI_API_KEY=...         (Google AI Studio — used by edge functions; optional client-side fallback)
 *
 * The schema expected matches your provided PostgreSQL schema (papers, paper_summaries,
 * folders, user_papers, feed_items, citation_edges, users).
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isSupabaseConfigured = Boolean(url && key);

export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(url!, key!)
  : null;

import type { Folder, Paper, PaperSummary, UserPaper } from "./types";

/**
 * Ensures a user record exists in the public.users table matching the auth user.
 */
export async function ensureUserExists(authUser: { id: string; email: string }) {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from("users")
    .upsert(
      { id: authUser.id, email: authUser.email },
      { onConflict: "email" }
    )
    .select()
    .single();

  if (error) {
    console.error("Failed to ensure user exists:", error);
    return null;
  }
  return data;
}

export async function getFolders(): Promise<Folder[]> {
  if (!supabase) return [];
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return [];
  
  const { data, error } = await supabase
    .from("folders")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });
    
  if (error) throw error;
  return data ?? [];
}

export async function createFolder(name: string): Promise<Folder> {
  if (!supabase) throw new Error("Supabase not configured");
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) throw new Error("Not authenticated");
  
  const { data, error } = await supabase
    .from("folders")
    .insert({ name, user_id: user.id })
    .select()
    .single();
    
  if (error) throw error;
  return data as Folder;
}

export async function deleteFolder(folderId: string): Promise<void> {
  if (!supabase) return;
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;
  
  const { error } = await supabase
    .from("folders")
    .delete()
    .eq("id", folderId)
    .eq("user_id", user.id);
    
  if (error) throw error;
}

export async function savePaperToFolder(paper: Paper, folderId: string): Promise<string> {
  if (!supabase) throw new Error("Supabase not configured");
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) throw new Error("Not authenticated");

  // Step A: Upsert paper into papers table
  const payload = {
    title: paper.title,
    authors: paper.authors ?? [],
    year: paper.year ?? null,
    abstract: paper.abstract ?? null,
    citation_count: paper.citation_count ?? 0,
    semantic_scholar_id: paper.semantic_scholar_id ?? null,
    arxiv_id: paper.arxiv_id ?? null,
    doi: paper.doi ?? null,
    open_access_url: paper.open_access_url ?? null,
    updated_at: new Date().toISOString(),
  };

  const { data: storedPaper, error: paperError } = await supabase
    .from("papers")
    .upsert(payload, { 
      onConflict: "semantic_scholar_id",
      ignoreDuplicates: false
    })
    .select()
    .single();

  if (paperError) throw paperError;

  // Step B: Link to user's folder
  // We first check if it exists to avoid requiring a specific UNIQUE constraint setup
  const { data: existingLink } = await supabase
    .from("user_papers")
    .select("id")
    .eq("user_id", user.id)
    .eq("paper_id", storedPaper.id)
    .eq("folder_id", folderId)
    .maybeSingle();

  if (!existingLink) {
    const { error: userPaperError } = await supabase
      .from("user_papers")
      .insert({
        user_id: user.id,
        paper_id: storedPaper.id,
        folder_id: folderId,
        status: "unread",
        saved_at: new Date().toISOString(),
      });

    if (userPaperError) throw userPaperError;
  }

  return storedPaper.id;
}

export async function savePaperSummary(paperId: string, summary: PaperSummary): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase
    .from("paper_summaries")
    .upsert(
      {
        paper_id: paperId,
        problem: summary.problem,
        method: summary.method,
        findings: summary.findings,
        limitations: summary.limitations,
        significance: summary.significance,
      },
      { onConflict: "paper_id" }
    );
  if (error) throw error;
}

export async function getPapersInFolder(folderId: string): Promise<(UserPaper & { paper: Paper })[]> {
  if (!supabase) return [];
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return [];

  const { data, error } = await supabase
    .from("user_papers")
    .select("*, paper:papers(*)")
    .eq("folder_id", folderId)
    .eq("user_id", user.id)
    .order("saved_at", { ascending: false });

  if (error) throw error;
  return (data ?? []) as (UserPaper & { paper: Paper })[];
}

export async function updateReadingStatus(userPaperId: string, status: "unread" | "in_progress" | "done") {
  if (!supabase) return;
  const { error } = await supabase
    .from("user_papers")
    .update({ status })
    .eq("id", userPaperId);
  if (error) throw error;
}
