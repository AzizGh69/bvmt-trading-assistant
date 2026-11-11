"use client";

import { useState, type FormEvent } from "react";
import { BookOpen, Send } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

interface Reply {
  configured: boolean;
  answer: string | null;
  error?: string;
  sources: { title: string; source: string; score: number }[];
  excerpts?: string[];
  tickers: string[];
  portfolio: boolean;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
  reply?: Reply;
}

const STARTERS = [
  "Pourquoi l’allocation optimisée fait-elle moins bien que les parts égales ?",
  "Comment lire la VaR de mon portefeuille ?",
  "Que disent les chiffres sur SFBT ?",
  "Comment les agents décident-ils d’acheter ?",
];

export default function AssistantPage() {
  const { user } = useAuth();
  const status = useApi<{ configured: boolean; model: string | null }>("/api/assistant/status");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function ask(question: string, event?: FormEvent) {
    event?.preventDefault();
    if (!question.trim() || busy) return;
    const history = [...turns, { role: "user" as const, content: question.trim() }];
    setTurns(history);
    setText("");
    setBusy(true);
    try {
      const messages = history
        .filter((t) => t.role === "user" || t.content)
        .map((t) => ({ role: t.role, content: t.content }));
      const reply = await api.post<Reply>("/api/assistant/chat", { messages });
      setTurns([...history, { role: "assistant", content: reply.answer ?? "", reply }]);
    } catch (e) {
      setTurns([...history, { role: "assistant", content: "", reply: undefined }]);
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Assistant"
        description="Questions sur la BVMT, sur les méthodes de l’application et sur votre portefeuille simulé."
      >
        {status.data && (
          <Badge variant={status.data.configured ? "success" : "warning"}>
            {status.data.configured ? `Modèle : ${status.data.model}` : "Aucun modèle de langage configuré"}
          </Badge>
        )}
      </PageHeader>

      <Card className="min-h-[420px] flex flex-col">
        <div className="flex-1 space-y-4">
          {turns.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted">
                {user
                  ? "L’assistant voit vos positions simulées et les chiffres des valeurs que vous citez."
                  : "Connectez-vous pour que l’assistant tienne compte de votre portefeuille simulé."}
              </p>
              <div className="flex flex-wrap gap-2">
                {STARTERS.map((s) => (
                  <Button key={s} size="sm" variant="outline" onClick={() => ask(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {turns.map((turn, i) => (
            <div key={i} className={cn("flex", turn.role === "user" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-xl px-4 py-3 text-sm",
                  turn.role === "user" ? "bg-accent text-white" : "bg-card-hover text-foreground"
                )}
              >
                {turn.role === "user" ? turn.content : <AssistantTurn reply={turn.reply} />}
              </div>
            </div>
          ))}
          {busy && <p className="text-sm text-muted">L’assistant cherche…</p>}
        </div>
        <form onSubmit={(e) => ask(text, e)} className="mt-4 flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} placeholder="Votre question…" />
          <Button type="submit" disabled={busy || !text.trim()}>
            <Send className="w-4 h-4" />
          </Button>
        </form>
      </Card>
      <p className="text-[11px] text-muted">Réponses générées à partir de calculs sur l’historique : pas un conseil en investissement.</p>
    </div>
  );
}

function AssistantTurn({ reply }: { reply?: Reply }) {
  if (!reply) return <p className="text-danger">L’assistant n’a pas pu répondre.</p>;
  return (
    <div className="space-y-3">
      {reply.answer ? (
        <p className="whitespace-pre-wrap">{reply.answer}</p>
      ) : reply.configured ? (
        <p className="text-danger">Le modèle de langage n’a pas répondu. Voici ce que dit la documentation :</p>
      ) : (
        <p className="text-muted">
          Aucun modèle de langage n’est configuré (variable LLM_API_KEY), donc pas de réponse rédigée. Voici les passages de la
          documentation les plus proches de votre question :
        </p>
      )}
      {!reply.answer &&
        reply.excerpts?.map((excerpt, i) => (
          <blockquote key={i} className="border-l-2 border-accent pl-3 text-muted">
            <p className="text-foreground font-medium text-xs mb-1">{reply.sources[i]?.title}</p>
            {excerpt}
          </blockquote>
        ))}
      {!reply.answer && !reply.excerpts?.length && <p className="text-muted">Aucun passage ne correspond.</p>}
      {reply.answer && reply.sources.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          <BookOpen className="w-3 h-3" />
          {reply.sources.map((s) => s.title).join(" · ")}
          {reply.portfolio ? " · votre portefeuille" : ""}
          {reply.tickers.length ? ` · ${reply.tickers.join(", ")}` : ""}
        </p>
      )}
    </div>
  );
}
