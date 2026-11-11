"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { AlertList, SEVERITY_LABEL } from "@/components/alert-list";
import { ErrorNote, Loading } from "@/components/states";
import { useApi } from "@/lib/use-api";
import type { AlertsResponse, MarketAlert } from "@/lib/api";
import { formatDate } from "@/lib/utils";

const PERIODS = [
  { id: "5", label: "5 séances" },
  { id: "20", label: "20 séances" },
  { id: "60", label: "60 séances" },
  { id: "250", label: "1 an" },
];

const LEVELS = [
  { id: "medium", label: "Moyenne et plus" },
  { id: "high", label: "Élevée et plus" },
  { id: "low", label: "Toutes" },
];

const ORDER: MarketAlert["severity"][] = ["critical", "high", "medium", "low"];
const TONE: Record<MarketAlert["severity"], string> = {
  critical: "text-danger",
  high: "text-warning",
  medium: "text-accent-light",
  low: "text-muted",
};

export default function SurveillancePage() {
  const [sessions, setSessions] = useState("20");
  const [level, setLevel] = useState("medium");
  const { data, error, loading } = useApi<AlertsResponse>(
    `/api/anomalies?sessions=${sessions}&min_severity=${level}&limit=200`
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Surveillance"
        description={data ? `Séances inhabituelles jusqu’au ${formatDate(data.session)}` : "Séances inhabituelles"}
      >
        <Tabs tabs={PERIODS} defaultTab={sessions} onChange={setSessions} />
      </PageHeader>

      {error ? (
        <ErrorNote message={error} />
      ) : !data ? (
        <Loading label="Analyse du marché…" />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {ORDER.map((severity) => (
              <Card key={severity}>
                <p className="text-[11px] uppercase tracking-wider text-muted">{SEVERITY_LABEL[severity]}</p>
                <p className={`mt-2 text-2xl font-bold tabular-nums ${TONE[severity]}`}>{data.by_severity[severity]}</p>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>
                {data.total} séance{data.total > 1 ? "s" : ""} signalée{data.total > 1 ? "s" : ""}
                {loading ? " · mise à jour…" : ""}
              </CardTitle>
              <Tabs tabs={LEVELS} defaultTab={level} onChange={setLevel} />
            </CardHeader>
            <AlertList alerts={data.alerts} />
          </Card>

          <Card>
            <CardTitle>Comment une séance est signalée</CardTitle>
            <ul className="mt-3 space-y-1.5 text-sm text-muted list-disc pl-5">
              <li>Pic de volume : plus de 3 écarts-types au-dessus des 60 séances précédentes de la valeur.</li>
              <li>Variation de cours : clôture à plus de 5 % de la clôture précédente.</li>
              <li>
                Profil inhabituel : une forêt d’isolement repère les séances dont la combinaison rendement, volume et
                amplitude s’écarte des habitudes de la valeur.
              </li>
              <li>
                Au-delà de 15 %, la variation est classée « opération sur titres » : les cours ne sont pas ajustés des
                divisions et attributions gratuites.
              </li>
            </ul>
            <p className="mt-3 text-[11px] text-muted">
              Un signalement est une invitation à regarder, pas une preuve de manipulation.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
