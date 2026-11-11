"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogIn, LogOut, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { NAV, isActive } from "@/lib/nav";
import { ThemeToggle } from "@/components/theme-toggle";

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  return (
    <aside className="hidden md:flex flex-col w-[220px] border-r border-border bg-sidebar shrink-0">
      <Link href="/" className="flex items-center gap-2.5 px-5 h-16 border-b border-border">
        <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
          <TrendingUp className="w-4 h-4 text-white" />
        </div>
        <div className="leading-tight">
          <span className="text-sm font-semibold text-foreground tracking-tight">BVMT</span>
          <span className="block text-[10px] text-muted tracking-widest uppercase">Trading Assistant</span>
        </div>
      </Link>

      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
              isActive(pathname, href)
                ? "bg-accent/10 text-accent-light"
                : "text-muted hover:text-foreground hover:bg-card-hover"
            )}
          >
            <Icon className="w-[18px] h-[18px]" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-border space-y-3">
        <div className="flex items-center justify-between gap-2">
          {user ? (
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 shrink-0 rounded-full bg-accent/20 flex items-center justify-center text-xs font-semibold text-accent-light">
                {user.username.slice(0, 1).toUpperCase()}
              </div>
              <span className="text-xs text-foreground font-medium truncate">{user.username}</span>
            </div>
          ) : (
            <Link href="/login" className="flex items-center gap-2 text-xs font-medium text-accent-light hover:underline">
              <LogIn className="w-4 h-4" />
              Se connecter
            </Link>
          )}
          <div className="flex items-center">
            <ThemeToggle />
            {user && (
              <button
                onClick={signOut}
                className="text-muted hover:text-foreground transition-colors p-2"
                title="Se déconnecter"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        <p className="text-[10px] text-muted leading-relaxed">
          Cours BVMT 2016–2026. Projet éducatif : rien ici n’est un conseil en investissement.
        </p>
      </div>
    </aside>
  );
}
