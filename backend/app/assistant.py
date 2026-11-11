"""The assistant: retrieval over the knowledge base, plus what the app knows about the user.

Retrieval is TF-IDF over the sections of ``knowledge/*.md`` (no embedding model
to download). The answer comes from the configured LLM, given the retrieved
sections, the user's paper portfolio when signed in, and the figures of any
stock the question names. Without an LLM it says so and still returns the
sections it found, so the documentation stays searchable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session

from . import llm
from .account import snapshot
from .analytics.forecasting import NotEnoughHistory, cached_forecast
from .analytics.indicators import technical_summary
from .analytics.market import MarketData
from .analytics.sentiment import tickers_in
from .analytics.tunizi import tokens
from .config import get_settings
from .models import User

KNOWLEDGE = Path(__file__).parent / "knowledge"
MIN_SCORE = 0.05

SYSTEM = (
    "Tu es l'assistant d'une application éducative sur la Bourse de Tunis (BVMT). Réponds en français, "
    "brièvement et concrètement, en t'appuyant uniquement sur le CONTEXTE fourni (documentation de "
    "l'application, portefeuille simulé de l'utilisateur, chiffres des valeurs citées). Si le contexte ne "
    "permet pas de répondre, dis-le. Ne donne jamais de conseil d'investissement personnalisé ni de "
    "garantie de performance : présente les chiffres comme des calculs sur l'historique, avec leurs "
    "limites. Les ordres du portefeuille sont fictifs."
)


@dataclass(frozen=True)
class Section:
    title: str
    text: str
    source: str


def load_sections(folder: Path = KNOWLEDGE) -> list[Section]:
    sections = []
    for path in sorted(folder.glob("*.md")):
        for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
            title, _, body = block.partition("\n")
            sections.append(Section(title.strip(), " ".join(body.split()), path.name))
    return sections


class Index:
    def __init__(self, sections: list[Section]):
        self.sections = sections
        # Accents folded and words tokenised the same way as the sentiment lexicon.
        self.vectorizer = TfidfVectorizer(tokenizer=tokens, lowercase=False, token_pattern=None, ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform([f"{s.title} {s.title} {s.text}" for s in sections])

    def search(self, query: str, k: int = 3) -> list[dict]:
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        best = scores.argsort()[::-1][:k]
        return [
            {"title": self.sections[i].title, "text": self.sections[i].text, "source": self.sections[i].source, "score": round(float(scores[i]), 3)}
            for i in best
            if scores[i] >= MIN_SCORE
        ]


@lru_cache
def get_index() -> Index:
    return Index(load_sections())


def portfolio_context(db: Session, user: User, market: MarketData) -> str:
    acct = snapshot(db, user, market, get_settings().risk_free_rate)
    lines = [
        f"Profil de risque : {user.risk_profile}. Séance : {acct['session']}.",
        f"Valeur totale {acct['total_value']} TND (départ {acct['initial_capital']}, résultat {acct['pnl_pct']} %), "
        f"liquidités {acct['cash']} TND.",
    ]
    for p in acct["positions"]:
        lines.append(f"- {p['ticker']} ({p['sector']}) : {p['quantity']} titres, {p['weight_pct']} % du compte, {p['pnl_pct']} % de plus/moins-value")
    if acct["risk"]:
        r = acct["risk"]
        lines.append(f"Risque des positions (250 séances) : volatilité {r['volatility_pct']} %, perte max {r['max_drawdown_pct']} %, VaR95 {r['var95_pct']} %.")
    if not acct["positions"]:
        lines.append("Aucune position.")
    return "\n".join(lines)


def stock_context(market: MarketData, ticker: str) -> str:
    history = market.history(ticker)
    last = history.iloc[-1]
    tech = technical_summary(history)
    line = f"{ticker} : clôture {float(last['close'])} TND le {last['date'].date()}, RSI {tech.get('rsi')}, MACD histogramme {tech.get('macd_histogram')}."
    try:
        f = cached_forecast(market, ticker, 5)
        verdict = "bat" if f["model"]["beats_random_walk"] else "ne bat pas"
        line += (
            f" Prévision 5 séances ({f['model']['selected']}, qui {verdict} la marche aléatoire au backtest) : "
            f"{f['expected_return_pct']} %, intervalle 80 % [{f['forecast'][-1]['lower80']} ; {f['forecast'][-1]['upper80']}] TND."
        )
    except NotEnoughHistory:
        line += " Historique trop court pour une prévision."
    return line


def answer(db: Session, market: MarketData, messages: list[dict], user: User | None) -> dict:
    question = messages[-1]["content"]
    sources = get_index().search(question)
    tickers = tickers_in(question, market)[:3]
    context = ["DOCUMENTATION :"] + [f"[{s['title']}] {s['text']}" for s in sources]
    if user:
        context += ["", "PORTEFEUILLE SIMULÉ DE L'UTILISATEUR :", portfolio_context(db, user, market)]
    if tickers:
        context += ["", "VALEURS CITÉES :"] + [stock_context(market, t) for t in tickers]
    used = {"sources": [{k: s[k] for k in ("title", "source", "score")} for s in sources], "tickers": tickers, "portfolio": user is not None}
    try:
        reply = llm.chat(
            [{"role": "system", "content": SYSTEM}, {"role": "system", "content": "CONTEXTE\n" + "\n".join(context)}]
            + [{"role": m["role"], "content": m["content"]} for m in messages[-8:]],
            temperature=0.2,
            max_tokens=600,
        )
    except llm.LLMNotConfigured:
        return {"configured": False, "answer": None, **used, "excerpts": [s["text"] for s in sources]}
    except llm.LLMError as exc:
        return {"configured": True, "answer": None, "error": str(exc), **used, "excerpts": [s["text"] for s in sources]}
    return {"configured": True, "answer": reply.strip(), **used}
