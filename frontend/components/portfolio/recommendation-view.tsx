"use client";

import Link from "next/link";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChartTooltip } from "@/components/ui/chart-tooltip";
import { StressList } from "@/components/portfolio/stress-list";
import type { Recommendation, RiskMetrics } from "@/lib/api";
import { PROFILE_LABEL, REASON_LABEL } from "@/lib/profiles";
import { formatCurrency, formatDate, sectorLabel } from "@/lib/utils";

const pct = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "–" : `${v.toFixed(digits)} %`);
const num = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toFixed(2));

export function RecommendationView({ plan }: { plan: Recommendation }) {
  const chosen = { volatility_pct: plan.expected.volatility_pct, return_pct: plan.expected.return_pct };
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Figure label="Rendement attendu" value={pct(plan.expected.return_pct)} note="par an, estimation shrinkée" />
        <Figure label="Volatilité attendue" value={pct(plan.expected.volatility_pct)} note="par an" />
        <Figure label="Lignes" value={String(plan.holdings.length)} note={`parmi ${plan.universe.stocks} valeurs liquides`} />
        <Figure
          label="Perte max. (période d’estimation)"
          value={pct(plan.in_sample.max_drawdown_pct)}
          note={`${plan.universe.lookback_sessions} séances`}
        />
      </div>

      <HonestyCard plan={plan} />

      <Card padding={false}>
        <div className="p-5 pb-3">
          <CardTitle>Allocation du profil {PROFILE_LABEL[plan.profile].toLowerCase()}</CardTitle>
          <p className="text-xs text-muted mt-1">
            Markowitz long-only : maximise rendement attendu − {plan.assumptions.risk_aversion / 2} × variance, au plus{" "}
            {Math.round(plan.assumptions.max_weight * 100)} % par valeur. Covariance Ledoit-Wolf, rendements moyens tirés à{" "}
            {Math.round(plan.assumptions.mean_shrinkage * 100)} % vers la moyenne du marché.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wider text-muted border-y border-border">
                <th className="text-left font-medium px-5 py-2">Valeur</th>
                <th className="text-right font-medium px-3 py-2">Poids</th>
                {plan.holdings[0]?.shares !== undefined && <th className="text-right font-medium px-3 py-2">Titres</th>}
                <th className="text-right font-medium px-3 py-2">Part du rendement</th>
                <th className="text-right font-medium px-3 py-2">Part du risque</th>
                <th className="text-left font-medium px-5 py-2">Rôle</th>
              </tr>
            </thead>
            <tbody>
              {plan.holdings.map((h) => (
                <tr key={h.ticker} className="border-b border-border last:border-0 hover:bg-card-hover">
                  <td className="px-5 py-2.5">
                    <Link href={`/valeurs/${h.ticker}`} className="font-medium text-foreground hover:text-accent-light">
                      {h.ticker}
                    </Link>
                    <span className="block text-[11px] text-muted truncate max-w-[220px]">{sectorLabel(h.sector)}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{h.weight_pct.toFixed(1)} %</td>
                  {h.shares !== undefined && (
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {h.shares}
                      <span className="block text-[11px] text-muted">{formatCurrency(h.amount_tnd ?? 0)}</span>
                    </td>
                  )}
                  <td className="px-3 py-2.5 text-right tabular-nums">{h.return_contribution_pct.toFixed(2)} pt</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{h.risk_share_pct.toFixed(1)} %</td>
                  <td className="px-5 py-2.5">
                    <Badge variant={h.reason === "diversifier" ? "success" : h.reason === "return_driver" ? "default" : "muted"}>
                      {REASON_LABEL[h.reason]}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="px-5 py-3 text-[11px] text-muted border-t border-border">
          Part du rendement : poids × rendement attendu (les parts s’additionnent au rendement du portefeuille). Part du risque :
          contribution d’Euler à la variance (les parts font 100 %). « Diversifie » : prend moins de risque que son poids.
        </p>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Frontière efficiente</CardTitle>
          </CardHeader>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="volatility_pct" name="Volatilité" unit=" %" tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <YAxis type="number" dataKey="return_pct" name="Rendement" unit=" %" tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <ZAxis range={[40, 40]} />
                <Tooltip content={<ChartTooltip formatter={(v) => `${v.toFixed(2)} %`} />} />
                <Scatter name="Frontière" data={plan.frontier} fill="var(--color-muted)" line={{ stroke: "var(--color-muted)" }} />
                <Scatter name="Ce profil" data={[chosen]} fill="var(--color-accent-light)" shape="star" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-[11px] text-muted">
            Chaque point est l’optimum pour une aversion au risque ; l’étoile est ce profil. Volatilité et rendement attendus, par an.
          </p>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Résistance aux chocs</CardTitle>
          </CardHeader>
          <StressList tests={plan.stress_tests} />
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Cette allocation sur la période d’estimation (base 100)</CardTitle>
        </CardHeader>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={plan.history} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
              <defs>
                <linearGradient id="planFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-accent-light)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--color-accent-light)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickFormatter={(d) => d.slice(0, 7)} tick={{ fontSize: 11 }} minTickGap={40} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} />
              <Tooltip content={<ChartTooltip formatter={(v) => v.toFixed(1)} />} />
              <Area type="monotone" dataKey="value" name="Valeur" stroke="var(--color-accent-light)" strokeWidth={2} fill="url(#planFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-muted">
          Rejoué sur les séances qui ont servi à choisir les poids : ce graphique est flatteur par construction. Voir le test hors
          échantillon plus haut.
        </p>
      </Card>
    </div>
  );
}

function Figure({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <Card>
      <p className="text-[11px] uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">{value}</p>
      <p className="text-[11px] text-muted mt-0.5">{note}</p>
    </Card>
  );
}

/** In-sample next to out-of-sample next to equal weight, and a sentence that says which won. */
function HonestyCard({ plan }: { plan: Recommendation }) {
  const check = plan.out_of_sample;
  if (!check) return null;
  const columns: { label: string; sub: string; metrics: RiskMetrics }[] = [
    {
      label: "Optimisé, période d’estimation",
      sub: `${plan.universe.lookback_sessions} séances jusqu’au ${formatDate(plan.session)}`,
      metrics: plan.in_sample,
    },
    {
      label: "Optimisé, hors échantillon",
      sub: `choisi jusqu’au ${formatDate(check.chosen_on[1])}, mesuré ensuite`,
      metrics: check.portfolio,
    },
    { label: "Parts égales, même période", sub: `${plan.universe.stocks} valeurs à poids égal`, metrics: check.equal_weight },
  ];
  const optimised = check.portfolio.sharpe ?? -Infinity;
  const equal = check.equal_weight.sharpe ?? -Infinity;
  const lost = optimised < equal;

  return (
    <Card className={lost ? "border-warning/50" : undefined}>
      <CardTitle>Ce que vaut l’optimisation, mesuré honnêtement</CardTitle>
      <p className="text-sm text-muted mt-1">
        Les poids ont été recalculés sur la première moitié de l’historique ({formatDate(check.chosen_on[0])} –{" "}
        {formatDate(check.chosen_on[1])}) puis tenus sur la seconde ({formatDate(check.scored_on[0])} –{" "}
        {formatDate(check.scored_on[1])}), qu’ils n’avaient jamais vue.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-muted border-b border-border">
              <th className="text-left font-medium py-2 pr-3" />
              {columns.map((c) => (
                <th key={c.label} className="text-right font-medium py-2 px-3">
                  {c.label}
                  <span className="block normal-case tracking-normal text-[10px]">{c.sub}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["Rendement annualisé", (m: RiskMetrics) => pct(m.annual_return_pct)],
                ["Volatilité", (m: RiskMetrics) => pct(m.volatility_pct)],
                ["Ratio de Sharpe", (m: RiskMetrics) => num(m.sharpe)],
                ["Perte maximale", (m: RiskMetrics) => pct(m.max_drawdown_pct)],
                ["VaR 95 % (1 séance)", (m: RiskMetrics) => pct(m.var95_pct, 2)],
              ] as const
            ).map(([label, show]) => (
              <tr key={label} className="border-b border-border last:border-0">
                <td className="py-2 pr-3 text-muted">{label}</td>
                {columns.map((c) => (
                  <td key={c.label} className="py-2 px-3 text-right tabular-nums">
                    {show(c.metrics)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={`mt-4 text-sm ${lost ? "text-warning" : "text-foreground"}`}>
        {lost
          ? "Hors échantillon, l’allocation optimisée a fait moins bien que la simple répartition à parts égales. Les rendements passés de la BVMT prédisent mal les suivants : lisez cette allocation comme un exercice de diversification et de mesure du risque, pas comme une promesse de performance."
          : "Hors échantillon, l’allocation optimisée a fait au moins aussi bien que les parts égales sur cette période. Une seule période ne prouve rien : ce n’est pas une promesse de performance."}
      </p>
    </Card>
  );
}
