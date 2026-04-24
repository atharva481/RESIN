import { AlertTriangle, ExternalLink } from "lucide-react";
import { isSupabaseConfigured } from "@/lib/supabase";
import { isNewsConfigured } from "@/lib/newsApi";
import { isGeminiConfigured } from "@/lib/gemini";

export function ConfigBanner() {
  const missing: string[] = [];
  if (!isSupabaseConfigured) missing.push("VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY");
  if (!isNewsConfigured) missing.push("VITE_NEWS_API_KEY");
  if (!isGeminiConfigured) missing.push("VITE_GEMINI_API_KEY");
  if (missing.length === 0) return null;

  return (
    <div className="mb-6 rounded-lg border border-accent/40 bg-accent/5 p-4 animate-fade-up">
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-accent/20 p-1.5">
          <AlertTriangle className="h-4 w-4 text-accent" />
        </div>
        <div className="flex-1 text-sm">
          <div className="font-medium mb-1">Connect your services to unlock the full app</div>
          <p className="text-muted-foreground mb-2">
            Create a <code className="text-xs bg-background px-1 py-0.5 rounded border">.env</code> file at the project root and add the following:
          </p>
          <pre className="text-xs bg-background border border-border rounded p-2 overflow-x-auto">
{missing.map((k) => `${k.split(" + ").map((s) => `${s}=…`).join("\n")}`).join("\n")}
          </pre>
          <div className="text-xs text-muted-foreground mt-2 flex flex-wrap gap-3">
            <a className="inline-flex items-center gap-1 hover:text-foreground transition-smooth" href="https://supabase.com/dashboard" target="_blank" rel="noreferrer">Supabase keys <ExternalLink className="h-3 w-3" /></a>
            <a className="inline-flex items-center gap-1 hover:text-foreground transition-smooth" href="https://newsapi.org/register" target="_blank" rel="noreferrer">NewsAPI key <ExternalLink className="h-3 w-3" /></a>
            <a className="inline-flex items-center gap-1 hover:text-foreground transition-smooth" href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">Gemini key <ExternalLink className="h-3 w-3" /></a>
          </div>
        </div>
      </div>
    </div>
  );
}
