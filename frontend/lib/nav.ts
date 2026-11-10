import { BarChart3, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown in the bottom bar on phones. */
  mobile?: boolean;
}

export const NAV: NavItem[] = [{ href: "/", label: "Marché", icon: BarChart3, mobile: true }];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" || pathname.startsWith("/valeurs") : pathname.startsWith(href);
}
