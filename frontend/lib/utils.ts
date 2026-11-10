import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(n);
}

export function formatCurrency(n: number): string {
  return `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)} TND`;
}

export function formatPercent(n: number): string {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function formatCompact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)} k`;
  return Math.round(n).toString();
}

/** "2026-02-06" -> "6 févr. 2026" */
export function formatDate(iso: string): string {
  const date = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? iso
    : new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "À l'instant";
  if (mins < 60) return `Il y a ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `Il y a ${hours}h`;
  const days = Math.floor(hours / 24);
  return `Il y a ${days}j`;
}

const SECTORS: Record<string, string> = {
  Automotive: "Automobile",
  Banks: "Banques",
  "Building materials": "Matériaux de construction",
  "Consumer goods": "Biens de consommation",
  "Financial services": "Services financiers",
  "Food & beverages": "Agroalimentaire",
  Health: "Santé",
  Holdings: "Holdings",
  "Industry & chemicals": "Industrie et chimie",
  Insurance: "Assurances",
  Leasing: "Leasing",
  Other: "Autres",
  "Real estate": "Immobilier",
  "Retail & distribution": "Distribution",
  "Technology & telecom": "Technologie et télécoms",
  Transport: "Transport",
};

/** French label of a sector name sent by the API. */
export function sectorLabel(sector: string): string {
  return SECTORS[sector] ?? sector;
}
