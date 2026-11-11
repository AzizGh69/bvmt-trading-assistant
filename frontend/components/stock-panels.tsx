"use client";

import { ForecastPanel } from "@/components/forecast-panel";
import type { HistoryRow } from "@/lib/api";

/** Per-stock panels beyond the price charts: forecast, then anomalies and agents. */
export function StockPanels({ ticker, history }: { ticker: string; history: HistoryRow[] }) {
  return (
    <>
      <ForecastPanel ticker={ticker} history={history} />
    </>
  );
}
