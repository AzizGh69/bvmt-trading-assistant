import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

export function Loading({ label = "Chargement…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-muted">
      <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      {label}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-danger/40 bg-danger/10 p-4 text-sm text-foreground">
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-danger" />
      <span>{message}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-muted">{children}</p>;
}

export function Change({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  if (value === null || value === undefined || Number.isNaN(value)) return <span className={`text-muted ${className}`}>–</span>;
  const tone = value > 0 ? "text-success" : value < 0 ? "text-danger" : "text-muted";
  return (
    <span className={`${tone} tabular-nums ${className}`}>
      {value > 0 ? "+" : ""}
      {value.toFixed(2)} %
    </span>
  );
}
