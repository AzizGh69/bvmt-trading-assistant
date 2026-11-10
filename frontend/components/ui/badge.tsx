import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "danger" | "warning" | "muted" | "info" | "outline" | "secondary";
  className?: string;
}

const VARIANTS: Record<string, string> = {
  default: "bg-accent/15 text-accent-light",
  success: "bg-success/15 text-success",
  danger: "bg-danger/15 text-danger",
  warning: "bg-warning/15 text-warning",
  muted: "bg-card-hover text-muted",
  info: "bg-blue-500/15 text-blue-400",
  outline: "border border-border bg-transparent text-foreground",
  secondary: "bg-card-hover text-foreground",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 text-[11px] font-medium rounded-md",
        VARIANTS[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
