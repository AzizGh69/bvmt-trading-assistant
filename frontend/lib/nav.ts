import { BarChart3, Bot, BriefcaseBusiness, MessageCircleQuestion, MessageSquareText, ShieldAlert, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown in the bottom bar on phones. */
  mobile?: boolean;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Marché", icon: BarChart3, mobile: true },
  { href: "/surveillance", label: "Surveillance", icon: ShieldAlert, mobile: true },
  { href: "/portefeuille", label: "Portefeuille", icon: BriefcaseBusiness, mobile: true },
  { href: "/agents", label: "Agents", icon: Bot, mobile: true },
  { href: "/sentiment", label: "Sentiment", icon: MessageSquareText },
  { href: "/assistant", label: "Assistant", icon: MessageCircleQuestion },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" || pathname.startsWith("/valeurs") : pathname.startsWith(href);
}
