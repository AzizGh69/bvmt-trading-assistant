"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowLeft } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/ui/tabs";
import { ChartTooltip } from "@/components/ui/chart-tooltip";
import { Change, ErrorNote, Loading } from "@/components/states";
import { StockPanels } from "@/components/stock-panels";
import { useApi } from "@/lib/use-api";
import type { StockDetail } from "@/lib/api";
import { formatCompact, formatDate, formatNumber, sectorLabel } from "@/lib/utils";

const RANGES = [
  { id: "120", label: "6 mois" },
  { id: "250", label: "1 an" },
  { id: "750", label: "3 ans" },
  { id: "3000", label: "Tout" },
];

function rsiState(rsi: number | null): { label: string; variant: "success" | "danger" | "muted" } {
  if (rsi === null) return { label: "indisponible", variant: "muted" };
  if (rsi < 30) return { label: "survente", variant: "success" };
  if (rsi > 70) return { label: "surachat", variant: "danger" };
  return { label: "neutre", variant: "muted" };
}

const dateTick = (d: string) => d.slice(2, 7);

export default function StockPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker);
  const [range, setRange] = useState("250");
  const { data, error, loading } = useApi<StockDetail>(`/api/stocks/${encodeURIComponent(ticker)}?sessions=${range}`);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorNote message={error ?? "Valeur introuvable."} />;

  const ind = data.indicators;
  const rsi = rsiState(ind.rsi);
  const macdUp = (ind.macd_histogram ?? 0) > 0;
  const band =
    ind.bb_percent_b === null
      ? "indisponible"
      : ind.bb_percent_b > 1
        ? "au-dessus de la bande haute"
        : ind.bb_percent_b < 0
          ? "sous la bande basse"
          : "dans les bandes";

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground mb-3">
          <ArrowLeft className="w-3.5 h-3.5" />
          Marché
        </Link>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-semibold tracking-tight">{data.ticker}</h1>
              <Badge variant="muted">{sectorLabel(data.sector)}</Badge>
              {!data.listed && <Badge variant="warning">plus cotée</Badge>}
            </div>
            <p className="text-sm text-muted mt-1">
              {data.isin} · séance du {formatDate(data.quote.session)}
              {!data.quote.traded && " · non traitée ce jour, dernier cours reporté"}
            </p>
          </div>
          <div className="md:text-right">
            <p className="text-3xl font-semibold tabular-nums">
              {data.quote.close.toFixed(3)} <span className="text-base text-muted font-normal">TND</span>
            </p>
            <Change value={data.quote.change_pct} className="text-sm" />
            <span className="text-xs text-muted">
              {" "}
              · {formatNumber(data.quote.volume)} titres · {formatCompact(data.quote.turnover)} TND
            </span>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Cours et bandes de Bollinger</CardTitle>
          <Tabs tabs={RANGES} defaultTab={range} onChange={setRange} />
        </CardHeader>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.history}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickFormatter={dateTick} minTickGap={48} tickLine={false} axisLine={false} />
              <YAxis domain={["auto", "auto"]} width={48} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip formatter={(v) => v.toFixed(3)} />} />
              <Line type="monotone" dataKey="bb_upper" name="Bande haute" stroke="var(--color-muted)" strokeDasharray="4 4" dot={false} strokeWidth={1} />
              <Line type="monotone" dataKey="bb_lower" name="Bande basse" stroke="var(--color-muted)" strokeDasharray="4 4" dot={false} strokeWidth={1} />
              <Line type="monotone" dataKey="sma_50" name="Moyenne 50" stroke="var(--color-warning)" dot={false} strokeWidth={1} />
              <Line type="monotone" dataKey="close" name="Clôture" stroke="var(--color-accent-light)" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-3 text-[11px] text-muted">
          Cours non ajustés des opérations sur titres (divisions, attributions gratuites) : une chute brutale isolée peut
          en être une.
        </p>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>RSI (14)</CardTitle>
            <Badge variant={rsi.variant}>
              {ind.rsi === null ? "–" : ind.rsi.toFixed(0)} · {rsi.label}
            </Badge>
          </CardHeader>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.history}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={dateTick} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} ticks={[0, 30, 50, 70, 100]} width={32} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip formatter={(v) => v.toFixed(1)} />} />
                <ReferenceLine y={70} stroke="var(--color-danger)" strokeDasharray="4 4" />
                <ReferenceLine y={30} stroke="var(--color-success)" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="rsi" name="RSI" stroke="var(--color-accent-light)" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>MACD (12, 26, 9)</CardTitle>
            <Badge variant={macdUp ? "success" : "danger"}>{macdUp ? "au-dessus du signal" : "sous le signal"}</Badge>
          </CardHeader>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.history}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={dateTick} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis width={40} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip formatter={(v) => v.toFixed(3)} />} />
                <Bar dataKey="histogram" name="Histogramme">
                  {data.history.map((row) => (
                    <Cell key={row.date} fill={(row.histogram ?? 0) >= 0 ? "var(--color-success)" : "var(--color-danger)"} fillOpacity={0.6} />
                  ))}
                </Bar>
                <Line type="monotone" dataKey="macd" name="MACD" stroke="var(--color-accent-light)" dot={false} strokeWidth={1.5} />
                <Line type="monotone" dataKey="signal" name="Signal" stroke="var(--color-warning)" dot={false} strokeWidth={1.5} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card>
        <CardTitle>Lecture technique</CardTitle>
        <dl className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <dt className="text-[11px] uppercase tracking-wider text-muted">Bollinger</dt>
            <dd className="mt-1">{band}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wider text-muted">Moyenne 20 séances</dt>
            <dd className="mt-1 tabular-nums">{ind.sma_20?.toFixed(3) ?? "–"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wider text-muted">Moyenne 50 séances</dt>
            <dd className="mt-1 tabular-nums">{ind.sma_50?.toFixed(3) ?? "–"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wider text-muted">Historique</dt>
            <dd className="mt-1">depuis le {formatDate(data.first_session)}</dd>
          </div>
        </dl>
      </Card>

      <StockPanels ticker={data.ticker} />
    </div>
  );
}
