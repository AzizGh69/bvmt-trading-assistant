"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Empty, ErrorNote } from "@/components/states";
import { api, type Article, type SentimentResult } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { relativeTime } from "@/lib/utils";

const LABEL = { positive: "Positif", negative: "Négatif", neutral: "Neutre" } as const;
const TONE = { positive: "success", negative: "danger", neutral: "muted" } as const;
const LANGUAGE = { fr: "Français", ar: "Arabe", tunizi: "Tunizi" } as Record<string, string>;
const EXAMPLES = [
  "BIAT : le bénéfice net progresse de 12 % en 2025",
  "SFBT ma tla3ch lyoum, bech ti7 2main",
  "تراجع أرباح الشركة وخسائر في الربع الأخير",
];

export default function SentimentPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<SentimentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const feed = useApi<{ scraping_enabled: boolean; articles: Article[] }>("/api/news?limit=50");

  async function analyse(event?: FormEvent, value = text) {
    event?.preventDefault();
    setError(null);
    try {
      setResult(await api.post<SentimentResult>("/api/sentiment/analyze", { text: value }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyse impossible");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Sentiment" description="Le ton d’un titre ou d’un message, en français, en arabe ou en tunizi." />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <form onSubmit={analyse} className="space-y-3">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              maxLength={2000}
              required
              placeholder="Collez un titre d’actualité ou un message…"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={text.trim().length < 3}>
                Analyser
              </Button>
              {EXAMPLES.map((example) => (
                <Button
                  key={example}
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setText(example);
                    analyse(undefined, example);
                  }}
                >
                  {example.slice(0, 22)}…
                </Button>
              ))}
            </div>
          </form>
          <p className="mt-3 text-[11px] text-muted">
            Avec une clé LLM configurée, le modèle note le texte ; sinon un lexique français / arabe / tunizi (chiffres arabizi compris) le fait.
            Rien n’est enregistré.
          </p>
        </Card>

        <Card>
          <CardTitle>Résultat</CardTitle>
          {error ? (
            <div className="mt-3">
              <ErrorNote message={error} />
            </div>
          ) : result ? (
            <div className="mt-3 space-y-3 text-sm">
              <div className="flex items-center gap-3">
                <Badge variant={TONE[result.label]} className="text-sm px-3 py-1">
                  {LABEL[result.label]}
                </Badge>
                <span className="tabular-nums">
                  {result.score > 0 ? "+" : ""}
                  {result.score.toFixed(2)}
                </span>
                <span className="text-xs text-muted">
                  {LANGUAGE[result.language]} · {result.method === "llm" ? "modèle de langage" : "lexique"}
                </span>
              </div>
              {result.reason && <p className="text-muted">{result.reason}</p>}
              {result.matches.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {result.matches.map((m, i) => (
                    <Badge key={i} variant={m.weight > 0 ? "success" : "danger"}>
                      {m.negated ? "¬ " : ""}
                      {m.term} {m.weight > 0 ? "+" : ""}
                      {m.weight.toFixed(1)}
                    </Badge>
                  ))}
                </div>
              )}
              <p className="text-xs text-muted">
                Valeurs citées :{" "}
                {result.tickers.length
                  ? result.tickers.map((t, i) => (
                      <span key={t}>
                        {i > 0 && ", "}
                        <Link href={`/valeurs/${t}`} className="text-accent-light hover:underline">
                          {t}
                        </Link>
                      </span>
                    ))
                  : "aucune reconnue"}
              </p>
            </div>
          ) : (
            <Empty>Analysez un texte pour voir son score.</Empty>
          )}
        </Card>
      </div>

      <Card padding={false}>
        <div className="p-5 pb-3">
          <CardTitle>Actualités lues</CardTitle>
        </div>
        {feed.data?.articles.length ? (
          <ul className="divide-y divide-border">
            {feed.data.articles.map((a) => (
              <li key={a.id} className="px-5 py-3 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <a href={a.url} target="_blank" rel="noreferrer noopener" className="text-sm hover:text-accent-light">
                    {a.title}
                  </a>
                  <p className="text-[11px] text-muted">
                    {a.source} · {relativeTime(a.published_at)}
                    {a.tickers.length ? ` · ${a.tickers.join(", ")}` : ""}
                  </p>
                </div>
                <Badge variant={TONE[a.label]}>{LABEL[a.label]}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            {feed.data && !feed.data.scraping_enabled
              ? "La lecture des flux d’actualités est désactivée (ENABLE_SCRAPING=false) : le signal « actualités » des agents reste absent."
              : "Aucun article pour l’instant."}
          </Empty>
        )}
      </Card>
    </div>
  );
}
