import { NavLink } from "@/components/NavLink";
import { Newspaper, BookOpen, FolderOpen, Network, Sparkles, LogOut, User } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useAuth } from "@/components/AuthProvider";
import { supabase } from "@/lib/supabase";

const items = [
  { to: "/", label: "Daily Feed", icon: Newspaper },
  { to: "/papers", label: "Paper Hub", icon: BookOpen },
  { to: "/library", label: "Library", icon: FolderOpen },
  { to: "/graph", label: "Connections", icon: Network },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const { user } = useAuth();
  
  return (
    <div className="min-h-screen w-full bg-background paper-grain">
      <div className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="hidden md:flex md:w-60 lg:w-64 flex-col border-r border-border bg-sidebar/60 backdrop-blur-sm">
          <div className="px-6 pt-6 pb-8">
            <NavLink to="/" className="flex items-center gap-2 group">
              <div className="h-9 w-9 rounded-md bg-gradient-ink flex items-center justify-center shadow-ink group-hover:scale-105 transition-smooth">
                <Sparkles className="h-4 w-4 text-paper" />
              </div>
              <div className="flex flex-col leading-tight">
                <span className="font-serif-display text-2xl font-semibold tracking-tight">RESIN</span>
                <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Research Intel</span>
              </div>
            </NavLink>
          </div>

          <nav className="flex-1 px-3 space-y-1">
            {items.map((it) => {
              const Icon = it.icon;
              return (
                <NavLink
                  key={it.to}
                  to={it.to}
                  end={it.to === "/"}
                  className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-smooth"
                  activeClassName="!bg-foreground !text-background shadow-ink"
                >
                  <Icon className="h-4 w-4" />
                  <span>{it.label}</span>
                </NavLink>
              );
            })}
          </nav>

          <div className="px-4 py-4 border-t border-border">
            {user ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 overflow-hidden">
                  <div className="h-8 w-8 rounded-full bg-secondary flex items-center justify-center shrink-0 overflow-hidden">
                    {user.user_metadata?.avatar_url ? (
                      <img src={user.user_metadata.avatar_url} alt="Avatar" className="h-full w-full object-cover" />
                    ) : (
                      <User className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="text-xs truncate">
                    <div className="font-medium text-foreground truncate">{user.user_metadata?.full_name || user.email}</div>
                    <div className="text-muted-foreground truncate" title={user.email}>{user.email}</div>
                  </div>
                </div>
                <button 
                  onClick={() => supabase?.auth.signOut()} 
                  className="p-1.5 shrink-0 text-muted-foreground hover:text-foreground hover:bg-secondary rounded transition-smooth ml-2"
                  title="Sign out"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            ) : null}
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0">
          {/* Mobile top bar */}
          <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-sidebar/60 backdrop-blur-sm">
            <NavLink to="/" className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-md bg-gradient-ink flex items-center justify-center">
                <Sparkles className="h-3.5 w-3.5 text-paper" />
              </div>
              <span className="font-serif-display text-lg font-semibold">RESIN</span>
            </NavLink>
            <nav className="flex gap-1 items-center">
              {items.map((it) => {
                const Icon = it.icon;
                const active = loc.pathname === it.to || (it.to !== "/" && loc.pathname.startsWith(it.to));
                return (
                  <NavLink
                    key={it.to}
                    to={it.to}
                    end={it.to === "/"}
                    className={`p-2 rounded-md transition-smooth ${active ? "bg-foreground text-background" : "text-muted-foreground hover:bg-sidebar-accent"}`}
                  >
                    <Icon className="h-4 w-4" />
                  </NavLink>
                );
              })}
              {user && (
                <button onClick={() => supabase?.auth.signOut()} className="p-2 ml-1 text-muted-foreground hover:bg-secondary rounded-md">
                  <LogOut className="h-4 w-4" />
                </button>
              )}
            </nav>
          </div>

          <div className="px-4 sm:px-8 lg:px-12 py-8 max-w-6xl mx-auto animate-fade-in">{children}</div>

          {user && (
            <button
              onClick={() => supabase?.auth.signOut()}
              className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-foreground text-background px-4 py-3 shadow-lg hover:bg-foreground/90 transition-smooth"
            >
              <LogOut className="h-4 w-4" />
              <span className="text-sm font-medium">Log out</span>
            </button>
          )}
        </main>
      </div>
    </div>
  );
}
