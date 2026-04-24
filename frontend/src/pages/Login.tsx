import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Sparkles, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/components/AuthProvider";

export default function Login() {
  const [loading, setLoading] = useState(false);
  const { user, loading: authLoading } = useAuth();

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  const handleLogin = async () => {
    setLoading(true);
    if (!supabase) {
      toast.error("Supabase is not configured. Check your .env file.");
      setLoading(false);
      return;
    }
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: window.location.origin,
      },
    });
    if (error) {
      toast.error(error.message);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background paper-grain p-4">
      <div className="w-full max-w-sm p-8 rounded-2xl border border-border bg-card shadow-sm text-center animate-fade-up">
        <div className="h-12 w-12 mx-auto rounded-xl bg-gradient-ink flex items-center justify-center shadow-ink mb-6">
          <Sparkles className="h-6 w-6 text-paper" />
        </div>
        <h1 className="font-serif-display text-2xl font-bold tracking-tight mb-2">Welcome to RESIN</h1>
        <p className="text-sm text-muted-foreground mb-8">Sign in to save papers, generate AI summaries, and build your connection graph.</p>
        
        <Button 
          className="w-full h-11" 
          onClick={handleLogin} 
          disabled={loading}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          Continue with Google
        </Button>
      </div>
    </div>
  );
}
