"""Sentiment of a text about a listed company: the LLM when configured, the lexicon otherwise."""
from __future__ import annotations

import re

from .. import llm
from .market import MarketData
from .tunizi import label_for, lexicon_sentiment, nickname_tickers

PROMPT = (
    "You rate the sentiment of financial news and social posts about companies listed on the "
    "Tunis Stock Exchange (BVMT). Texts may be in French, Modern Standard Arabic or Tunizi "
    "(Tunisian Arabic written in Latin letters, with digits for some letters: 3=ع, 7=ح, 9=ق, 5=خ). "
    "Rate what the text implies for the company's share price, from -1 (clearly bad) to 1 "
    "(clearly good), 0 when neutral or unrelated to the company's prospects. "
    'Answer only a JSON object: {"score": number, "reason": "at most 20 words, in French"}.'
)


def score_text(text: str) -> dict:
    """``{score, label, method, language, reason, matches}`` for one text."""
    lexicon = lexicon_sentiment(text)
    try:
        answer = llm.chat_json(
            [{"role": "system", "content": PROMPT}, {"role": "user", "content": text[:2000]}],
            temperature=0.0,
            max_tokens=120,
        )
        score = float(answer["score"])
        if not -1.0 <= score <= 1.0:
            raise ValueError("score out of range")
    except (llm.LLMNotConfigured, llm.LLMError, KeyError, TypeError, ValueError):
        return {**lexicon, "method": "lexicon", "reason": None}
    return {
        "score": round(score, 3),
        "label": label_for(score),
        "method": "llm",
        "language": lexicon["language"],
        "reason": str(answer.get("reason", ""))[:200] or None,
        "matches": lexicon["matches"],
    }


def tickers_in(text: str, market: MarketData) -> list[str]:
    """Listed tickers a text mentions, by symbol, company name or nickname."""
    found = set(nickname_tickers(text))
    upper = text.upper()
    listed = set(market.tickers())
    for ticker in listed:
        # Symbols are matched in capitals only, so "star" or "sits" in a sentence is not a stock,
        # and "BNA" does not match inside "BNA-ASSURANCES", nor "STA" inside "STAR".
        if re.search(rf"(?<![\w-]){re.escape(ticker)}(?![\w-])", text):
            found.add(ticker)
    stocks = market.stocks
    for ticker, name in zip(stocks["ticker"], stocks["name"]):
        if ticker in listed and len(name) >= 5 and re.search(rf"(?<![\w-]){re.escape(name.upper())}(?![\w-])", upper):
            found.add(ticker)
    return sorted(found)
