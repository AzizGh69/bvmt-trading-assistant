"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, ArrowDownRight, ArrowUpRight, Search } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { PageHeader } from "@/components/ui/page-header";
import { ChartTooltip } from "@/components/ui/chart-tooltip";
import { Input } from "@/components/ui/input";
import { Change, ErrorNote, Loading } from "@/components/states";
import { useApi } from "@/lib/use-api";
import type { Mover, Overview, Quote } from "@/lib/api";
import { formatCompact, formatDate, formatNumber, sectorLabel } from "@/lib/utils";

function MoverList({ title, rows }: { title: string; rows: Mover[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <ul className="space-y-2.5">
        {rows.map((row) => (
          <li key={row.ticker} className="flex items-center justify-between gap-3 text-sm">
            <Link href={`/valeurs/${encodeURIComponent(row.ticker)}`} className="min-w-0 hover:underline">
              <span className="font-medium text-foreground">{row.ticker}</span>
              <span className="block text-[11px] text-muted truncate">{sectorLabel(row.sector)}</span>
            </Link>
            <div className="text-right shrink-0">
              <span className="block tabular-nums text-foreground">{row.close.toFixed(3)}</span>
              <Change value={row.change_pct} className="text-xs" />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function MarketPage() {
  const overview = useApi<Overview>("/api/market/overview?top=5&sessions=250");
  const quotes = useApi<{ session: string; quotes: Quote[] }>("/api/market/quotes");
  const [filter, setFilter] = useState("");

  const rows = useMemo(() => {
    const all = quotes.data?.quotes ?? [];
    const needle = filter.trim().toLowerCase();
    return needle
      ? all.filter((q) => `${q.ticker} ${q.name} ${sectorLabel(q.sector)}`.toLowerCase().includes(needle))
      : all;
  }, [quotes.data, filter]);

  if (overview.loading) return <Loading />;
  if (overview.error || !overview.data) return <ErrorNote message={overview.error ?? "Aucune donnée."} />;
  const o = overview.data;

  return (
    <div className="space-y-6">
      <PageHeader title="Marché" description={`Séance du ${formatDate(o.session)} · Bourse de Tunis`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Indice composite"
          value={formatNumber(o.index.value)}
          sub={`${o.index.change_pct >= 0 ? "+" : ""}${o.index.change_pct.toFixed(2)} % sur la séance`}
          trend={o.index.change_pct > 0 ? "up" : o.index.change_pct < 0 ? "down" : "neutral"}
          icon={Activity}
        />
        <StatCard
          label="Hausses / baisses"
          value={`${o.breadth.advancing} / ${o.breadth.declining}`}
          sub={`${o.breadth.unchanged} inchangées · ${o.breadth.traded} valeurs traitées`}
          icon={ArrowUpRight}
        />
        <StatCard
          label="Capitaux échangés"
          value={`${formatCompact(o.totals.turnover)} TND`}
          sub={`${formatNumber(o.totals.trades)} transactions`}
          icon={ArrowDownRight}
        />
        <StatCard
          label="Volume"
          value={formatCompact(o.totals.volume)}
          sub={`${o.breadth.listed} valeurs cotées`}
          icon={Activity}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Indice composite BVMT, 250 séances</CardTitle>
          </CardHeader>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={o.index.history}>
                <defs>
                  <linearGradient id="indexFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-accent-light)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--color-accent-light)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(2, 7)} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis domain={["auto", "auto"]} width={52} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip formatter={(v) => formatNumber(v)} />} />
                <Area type="monotone" dataKey="value" name="Indice" stroke="var(--color-accent-light)" strokeWidth={2} fill="url(#indexFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-3 text-[11px] text-muted">
            Indice calculé à partir des cours, pondéré par la liquidité (base 1000 en 2016). Ce n’est pas le niveau
            officiel du TUNINDEX, que les fichiers de cours ne contiennent pas.
          </p>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Capitaux échangés par séance (TND)</CardTitle>
          </CardHeader>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={o.volume_history.slice(-60)}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} minTickGap={32} tickLine={false} axisLine={false} />
                <YAxis width={44} tickFormatter={(v: number) => formatCompact(v)} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip formatter={(v) => `${formatCompact(v)} TND`} />} cursor={{ fill: "var(--color-card-hover)" }} />
                <Bar dataKey="turnover" name="Capitaux" fill="var(--color-accent)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MoverList title="Plus fortes hausses" rows={o.gainers} />
        <MoverList title="Plus fortes baisses" rows={o.losers} />
        <MoverList title="Plus actives" rows={o.most_active} />
      </div>

      <Card padding={false}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-5 pb-3">
          <CardTitle>Toutes les valeurs</CardTitle>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Valeur ou secteur"
              className="pl-9 h-9"
              aria-label="Filtrer les valeurs"
            />
          </div>
        </div>
        {quotes.loading ? (
          <Loading />
        ) : quotes.error ? (
          <div className="p-5">
            <ErrorNote message={quotes.error} />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-y border-border">
                  <th className="px-5 py-2 font-medium">Valeur</th>
                  <th className="px-3 py-2 font-medium hidden md:table-cell">Secteur</th>
                  <th className="px-3 py-2 font-medium text-right">Clôture</th>
                  <th className="px-3 py-2 font-medium text-right">Variation</th>
                  <th className="px-3 py-2 font-medium text-right hidden sm:table-cell">Volume</th>
                  <th className="px-5 py-2 font-medium text-right hidden lg:table-cell">Capitaux (TND)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((q) => (
                  <tr key={q.ticker} className="border-b border-border last:border-0 hover:bg-card-hover">
                    <td className="px-5 py-2.5">
                      <Link href={`/valeurs/${encodeURIComponent(q.ticker)}`} className="font-medium text-foreground hover:underline">
                        {q.ticker}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-muted hidden md:table-cell">{sectorLabel(q.sector)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{q.close.toFixed(3)}</td>
                    <td className="px-3 py-2.5 text-right">
                      {q.traded ? <Change value={q.change_pct} /> : <span className="text-muted text-xs">non traitée</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums hidden sm:table-cell">{formatNumber(q.volume)}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums hidden lg:table-cell">{formatNumber(Math.round(q.turnover))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
