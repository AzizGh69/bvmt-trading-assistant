import Link from "next/link";
import { TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

/** The centred card the sign-in and sign-up pages share. */
export function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background">
      <div className="w-full max-w-md space-y-6">
        <Link href="/" className="flex items-center justify-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-accent flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <span className="text-base font-semibold text-foreground tracking-tight">BVMT Trading Assistant</span>
        </Link>
        <div className="rounded-xl border border-border bg-card p-6 space-y-5">
          <div>
            <h1 className="text-lg font-semibold text-foreground">{title}</h1>
            <p className="text-sm text-muted mt-1">{subtitle}</p>
          </div>
          {children}
        </div>
        <p className="text-center text-[11px] text-muted">
          Projet éducatif : un compte sert à simuler un portefeuille, jamais à passer de vrais ordres.
        </p>
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-foreground">{label}</span>
      {children}
    </label>
  );
}
