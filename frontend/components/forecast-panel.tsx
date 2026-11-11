"use client";

import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Change, ErrorNote, Loading } from "@/components/states";
import { useApi } from "@/lib/use-api";
import type { Forecast, HistoryRow } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/utils";

const MODEL_LABEL: Record<string, string> = {
  arima: "ARIMA",
  ema: "Moyenne exponentielle amortie",
  naive: "Marche aléatoire",
};

function modelName(forecast: Forecast, key: string): string {
  return key === "arima" ? `ARIMA(${forecast.model.arima_order.join(", ")})` : MODEL_LABEL[key];
}

export function ForecastPanel({ ticker, history }: { ticker: string; history: HistoryRow[] }) {
  const { data, error, loading } = useApi<Forecast>(`/api/stocks/${encodeURIComponent(ticker)}/forecast?horizon=5`);

  if (loading && !data) {
    return (
      <Card>
        <CardTitle>Prévision à 5 séances</CardTitle>
        <Loading label="Ajustement des modèles…" />
      </Card>
    );
  }
  if (error || !data) {
    return (
      <Card>
        <CardTitle>Prévision à 5 séances</CardTitle>
        <div className="mt-3">
          <ErrorNote message={error ?? "Prévision indisponible."} />
        </div>
      </Card>
    );
  }

  const recent = history.slice(-40).map((row) => ({ date: row.date, close: row.close }));
  const chart = [
    ...recent.slice(0, -1),
    // The last observed close anchors both the forecast line and its bands.
    { date: data.last_session, close: data.last_close, forecast: data.last_close, band80: [data.last_close, data.last_close], band95: [data.last_close, data.last_close] },
    ...data.forecast.map((p) => ({ date: p.date, forecast: p.price, band80: [p.lower80, p.upper80], band95: [p.lower95, p.upper95] })),
  ];
  const last = data.forecast[data.forecast.length - 1];
  const adfPrice = data.diagnostics.adf_log_price;
  const adfReturns = data.diagnostics.adf_log_returns;
  const models = data.backtest.models;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prévision à 5 séances</CardTitle>
        <Badge variant={data.model.beats_random_walk ? "success" : "muted"}>
          {modelName(data, data.model.selected)}
        </Badge>
      </CardHeader>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chart}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} minTickGap={32} tickLine={false} axisLine={false} />
                <YAxis domain={["auto", "auto"]} width={48} tickLine={false} axisLine={false} />
                <Tooltip
                  formatter={(value, name) => [
                    Array.isArray(value) ? `${Number(value[0]).toFixed(3)} – ${Number(value[1]).toFixed(3)}` : Number(value).toFixed(3),
                    name,
                  ]}
                  labelFormatter={(label) => formatDate(String(label))}
                  contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }}
                />
                <Area dataKey="band95" name="Intervalle 95 %" stroke="none" fill="var(--color-accent-light)" fillOpacity={0.12} />
                <Area dataKey="band80" name="Intervalle 80 %" stroke="none" fill="var(--color-accent-light)" fillOpacity={0.22} />
                <Line dataKey="close" name="Clôture" stroke="var(--color-foreground)" dot={false} strokeWidth={1.5} />
                <Line dataKey="forecast" name="Prévision" stroke="var(--color-accent-light)" strokeDasharray="5 4" dot={{ r: 2 }} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-sm">
            Le {formatDate(last.date)} : <span className="font-semibold tabular-nums">{last.price.toFixed(3)} TND</span>{" "}
            (<Change value={data.expected_return_pct} />
            ), entre {last.lower80.toFixed(3)} et {last.upper80.toFixed(3)} dans 80 % des cas.
          </p>
          <p className="mt-1 text-[11px] text-muted">
            {data.model.beats_random_walk
              ? "Sur les séances de test, ce modèle s’est moins trompé que la marche aléatoire."
              : "Aucun modèle n’a fait mieux que la marche aléatoire sur les séances de test : la prévision est le dernier cours."}{" "}
            Projet éducatif, pas un conseil en investissement.
          </p>
        </div>

        <div className="space-y-5 text-sm">
          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-muted mb-2">
              Test sur {data.backtest.span_sessions} séances non vues (erreur à {data.backtest.horizon} séances, TND)
            </h4>
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] text-muted">
                  <th className="font-medium pb-1">Modèle</th>
                  <th className="font-medium pb-1 text-right">RMSE</th>
                  <th className="font-medium pb-1 text-right">Sens juste</th>
                </tr>
              </thead>
              <tbody>
                {(["arima", "ema", "naive"] as const).map((key) => (
                  <tr key={key} className={key === data.model.selected ? "text-foreground font-medium" : "text-muted"}>
                    <td className="py-0.5">{modelName(data, key)}</td>
                    <td className="py-0.5 text-right tabular-nums">{models[key].rmse?.toFixed(4) ?? "–"}</td>
                    <td className="py-0.5 text-right tabular-nums">
                      {models[key].directional_accuracy === null ? "–" : `${Math.round(models[key].directional_accuracy * 100)} %`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-muted mb-2">Stationnarité (test ADF)</h4>
            <p>
              Cours : p = {adfPrice.p_value ?? "–"} ({adfPrice.stationary ? "stationnaire" : "non stationnaire"})
            </p>
            <p>
              Rendements : p = {adfReturns.p_value ?? "–"} ({adfReturns.stationary ? "stationnaires" : "non stationnaires"})
            </p>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-muted mb-2">Choix de l’ordre ARIMA</h4>
            <p>
              AIC : ({data.diagnostics.selected_by_aic?.join(", ") ?? "–"}) · BIC : ({data.diagnostics.selected_by_bic?.join(", ") ?? "–"})
            </p>
            <p className="text-[11px] text-muted mt-1">
              {data.diagnostics.candidates
                .slice(0, 3)
                .map((c) => `(${c.order.join(", ")}) AIC ${c.aic.toFixed(0)}`)
                .join(" · ")}
            </p>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-muted mb-2">Volume attendu par séance</h4>
            <p className="tabular-nums">
              {formatNumber(data.volume.expected)} titres ({formatNumber(data.volume.lower80)} – {formatNumber(data.volume.upper80)})
            </p>
            {data.volume.traded_probability !== null && (
              <p className="text-[11px] text-muted mt-1">
                Traitée {Math.round(data.volume.traded_probability * 100)} % des 60 dernières séances.
              </p>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
