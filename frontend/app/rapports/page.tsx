"use client";

import { useState } from "react";
import { Mail } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Empty, ErrorNote, Loading } from "@/components/states";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useApi } from "@/lib/use-api";
import { cn, formatDate } from "@/lib/utils";

interface ReportList {
  scheduler_enabled: boolean;
  smtp_configured: boolean;
  reports: { id: number; session: string; title: string }[];
}

interface Mailed {
  id: number;
  subject: string;
  body: string;
  status: "sent" | "not_configured" | "failed";
  created_at: string;
}

const STATUS = { sent: "Envoyé", not_configured: "Gardé ici (SMTP non configuré)", failed: "Échec d’envoi" };

export default function ReportsPage() {
  const { user, refresh } = useAuth();
  const list = useApi<ReportList>("/api/reports");
  const [chosen, setChosen] = useState<number | null>(null);
  const current = chosen ?? list.data?.reports[0]?.id ?? null;
  const report = useApi<{ title: string; body: string }>(current ? `/api/reports/${current}` : null);
  const inbox = useApi<Mailed[]>(user ? `/api/outbox?u=${user.id}` : null);
  const [message, setMessage] = useState<string | null>(null);

  async function runNow() {
    setMessage(null);
    try {
      const done = await api.post<{ already_done: boolean; alerts: number; emails: number; session: string }>("/api/reports/run");
      setMessage(
        done.already_done
          ? `Le rapport de la séance du ${formatDate(done.session)} existe déjà.`
          : `Rapport écrit : ${done.alerts} alerte(s), ${done.emails} e-mail(s).`
      );
      list.reload();
      inbox.reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Échec");
    }
  }

  async function toggleAlerts() {
    if (!user) return;
    await api.put("/api/auth/profile", { email_alerts: !user.email_alerts });
    await refresh();
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Rapports et alertes" description="Le compte rendu de chaque séance et les alertes envoyées par e-mail.">
        {user && (
          <Button size="sm" onClick={runNow}>
            Écrire le rapport de la dernière séance
          </Button>
        )}
      </PageHeader>
      {message && <p className="text-sm text-muted">{message}</p>}

      {list.error ? (
        <ErrorNote message={list.error} />
      ) : !list.data ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <Card className="lg:col-span-1">
            <CardTitle>Séances</CardTitle>
            {list.data.reports.length ? (
              <ul className="mt-3 space-y-1">
                {list.data.reports.map((r) => (
                  <li key={r.id}>
                    <button
                      onClick={() => setChosen(r.id)}
                      className={cn(
                        "w-full text-left px-2 py-1.5 rounded-md text-sm",
                        r.id === current ? "bg-accent/10 text-accent-light" : "text-muted hover:text-foreground"
                      )}
                    >
                      {formatDate(r.session)}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                Aucun rapport.{" "}
                {list.data.scheduler_enabled ? "Le prochain passage du planificateur en écrira un." : "Le planificateur est désactivé (ENABLE_SCHEDULER) : écrivez-le à la main une fois connecté."}
              </Empty>
            )}
          </Card>
          <Card className="lg:col-span-3">
            {report.data ? (
              <>
                <CardTitle>{report.data.title}</CardTitle>
                <pre className="mt-3 whitespace-pre-wrap font-sans text-sm text-foreground leading-relaxed">{report.data.body}</pre>
              </>
            ) : current ? (
              <Loading />
            ) : (
              <Empty>Choisissez une séance.</Empty>
            )}
          </Card>
        </div>
      )}

      {user && (
        <Card>
          <CardHeader>
            <CardTitle>Vos alertes par e-mail</CardTitle>
            <Button size="sm" variant={user.email_alerts ? "outline" : "default"} onClick={toggleAlerts}>
              <Mail className="w-3.5 h-3.5" /> {user.email_alerts ? "Ne plus recevoir" : "Recevoir les alertes"}
            </Button>
          </CardHeader>
          <p className="text-xs text-muted">
            {user.email_alerts
              ? "Après chaque séance : les séances inhabituelles sur vos valeurs, sinon les plus graves du marché, avec le rapport."
              : "Désactivées."}{" "}
            {list.data && !list.data.smtp_configured && "Aucun serveur SMTP n’est configuré : les messages sont gardés ci-dessous au lieu d’être envoyés."}
          </p>
          {inbox.data && inbox.data.length > 0 ? (
            <ul className="mt-4 divide-y divide-border">
              {inbox.data.map((m) => (
                <li key={m.id} className="py-3">
                  <details>
                    <summary className="cursor-pointer text-sm flex items-center justify-between gap-3">
                      <span>{m.subject}</span>
                      <Badge variant={m.status === "sent" ? "success" : m.status === "failed" ? "danger" : "muted"}>{STATUS[m.status]}</Badge>
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-xs text-muted">{m.body}</pre>
                  </details>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Aucun e-mail pour l’instant.</Empty>
          )}
        </Card>
      )}
    </div>
  );
}
