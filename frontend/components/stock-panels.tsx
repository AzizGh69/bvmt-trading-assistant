"use client";

import { ForecastPanel } from "@/components/forecast-panel";
import { AlertList } from "@/components/alert-list";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useApi } from "@/lib/use-api";
import type { AlertsResponse, HistoryRow } from "@/lib/api";

function StockAlerts({ ticker }: { ticker: string }) {
  const { data } = useApi<AlertsResponse & { ticker: string }>(
    `/api/stocks/${encodeURIComponent(ticker)}/anomalies?sessions=250&min_severity=low`
  );
  if (!data) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Séances inhabituelles sur un an</CardTitle>
        <Badge variant="muted">{data.total}</Badge>
      </CardHeader>
      <AlertList alerts={data.alerts.slice(0, 8)} showTicker={false} />
    </Card>
  );
}

/** Per-stock panels beyond the price charts: forecast, anomalies, then agents. */
export function StockPanels({ ticker, history }: { ticker: string; history: HistoryRow[] }) {
  return (
    <>
      <ForecastPanel ticker={ticker} history={history} />
      <StockAlerts ticker={ticker} />
    </>
  );
}
