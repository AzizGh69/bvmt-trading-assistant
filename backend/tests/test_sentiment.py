"""Lexicon sentiment (French, Arabic, Tunizi), the LLM path, ticker detection and the news feeds."""
from __future__ import annotations

import httpx
import pytest

from app import llm, news
from app.analytics import sentiment
from app.analytics.tunizi import detect_language, lexicon_sentiment, nickname_tickers, tokens
from app.config import Settings


def terms(text: str) -> list[str]:
    return [m["term"] for m in lexicon_sentiment(text)["matches"]]


def test_french_and_arabic_headlines():
    assert lexicon_sentiment("Le bénéfice de la banque progresse de 12 %")["label"] == "positive"
    assert lexicon_sentiment("Grève générale : chute de la production")["label"] == "negative"
    assert lexicon_sentiment("ارتفاع الأرباح")["label"] == "positive"  # the article "ال" is read through
    assert lexicon_sentiment("تراجع المبيعات وخسائر")["score"] < 0
    both = lexicon_sentiment("تراجع أرباح الشركة وخسائر")  # "profits fall" as one phrase, "and losses" through its prefix
    assert len(both["matches"]) == 2 and all(m["weight"] < 0 for m in both["matches"])
    assert lexicon_sentiment("La société publie son rapport annuel")["label"] == "neutral"


def test_tunizi_arabizi_and_phrases():
    result = lexicon_sentiment("SFBT bech ti7 2main")
    assert result["label"] == "negative" and result["language"] == "tunizi"
    assert terms("SFBT bech ti7 2main") == ["bech tih"]  # the phrase, not the phrase and "ti7" again
    assert lexicon_sentiment("Poulina tla3et lyoum, rbe7na")["score"] > 0.6
    assert tokens("cours 13,44 en 2026") == ["cours", "13", "44", "en", "2026"]  # numbers are not Arabizi


def test_negation_flips_a_word():
    assert lexicon_sentiment("Les résultats ne sont pas en hausse")["score"] < 0
    assert lexicon_sentiment("SFBT ma tla3ch")["score"] < 0  # Tunisian "ma ...ch"
    assert lexicon_sentiment("لا ارتفاع")["score"] < 0


def test_language_detection():
    assert detect_language("الأرباح ترتفع") == "ar"
    assert detect_language("Sah 9a3da tla3") == "tunizi"
    assert detect_language("Le marché termine en hausse") == "fr"


def test_tickers_by_symbol_name_and_nickname(market):
    assert nickname_tickers("La bière va monter") == {"SFBT"}
    assert sentiment.tickers_in("ALPHA et BETA publient leurs comptes", market) == ["ALPHA", "BETA"]
    assert sentiment.tickers_in("les résultats de Gamma", market) == ["GAMMA"]  # by name
    assert sentiment.tickers_in("ALPHA-BETA n'existe pas", market) == []
    assert sentiment.tickers_in("une beta de marché", market) == []  # symbols only in capitals, names >= 5 letters


def test_llm_is_used_when_configured_and_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda messages, **kw: {"score": 0.8, "reason": "Résultats en forte hausse"})
    scored = sentiment.score_text("SFBT annonce un dividende record")
    assert scored["method"] == "llm" and scored["label"] == "positive" and scored["reason"]

    def broken(messages, **kw):
        raise llm.LLMError("timeout")

    monkeypatch.setattr(llm, "chat_json", broken)
    assert sentiment.score_text("chute des ventes")["method"] == "lexicon"
    monkeypatch.setattr(llm, "chat_json", lambda messages, **kw: {"score": 7})
    assert sentiment.score_text("chute des ventes")["method"] == "lexicon"  # out of range is not trusted


def test_llm_client(monkeypatch):
    with pytest.raises(llm.LLMNotConfigured):
        llm.chat([{"role": "user", "content": "hi"}], settings=Settings(llm_api_key=""))
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, body=json, auth=headers["Authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"score": 0.1}'}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    settings = Settings(llm_api_key="k", llm_base_url="https://api.groq.com/openai/v1/", llm_model="m")
    assert llm.chat_json([{"role": "user", "content": "x"}], settings=settings) == {"score": 0.1}
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["body"]["model"] == "m" and seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["auth"] == "Bearer k"

    def failing(url, json, headers, timeout):
        return httpx.Response(429, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", failing)
    with pytest.raises(llm.LLMError) as error:
        llm.chat([{"role": "user", "content": "x"}], settings=settings)
    assert "k" not in str(error.value).split()


RSS = """<?xml version="1.0"?><rss><channel>
<item><title>BIAT : le bénéfice progresse</title><link>https://example.test/a</link>
<description>&lt;p&gt;Hausse de 10 %&lt;/p&gt;</description><pubDate>Mon, 02 Feb 2026 10:00:00 +0100</pubDate></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>ALPHA chute</title><link href="https://example.test/b"/><updated>2026-02-03T09:00:00Z</updated></entry>
</feed>"""


def test_parse_rss_and_atom():
    items = news.parse_feed(RSS, "example.test")
    assert len(items) == 1 and items[0]["summary"] == "Hausse de 10 %" and items[0]["published_at"].year == 2026
    atom = news.parse_feed(ATOM, "example.test")
    assert atom[0]["url"] == "https://example.test/b" and atom[0]["title"] == "ALPHA chute"


def test_scraping_is_opt_in_and_soft(monkeypatch):
    with pytest.raises(news.ScrapingDisabled):
        news.fetch_feeds(Settings(enable_scraping=False))

    def fake_get(url, **kw):
        if "broken" in url:
            raise httpx.ConnectTimeout("slow")
        return httpx.Response(200, text=RSS, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    settings = Settings(enable_scraping=True, news_feeds="https://ok.test/feed,https://broken.test/feed")
    articles, errors = news.fetch_feeds(settings)
    assert len(articles) == 1 and errors == ["broken.test: ConnectTimeout"]


def test_store_and_aggregate(client):
    from app.analytics.market import get_market
    from app.db import session_factory

    with session_factory()() as db:
        items = news.parse_feed(ATOM, "example.test") + [
            {"source": "x", "url": "https://example.test/c", "title": "ALPHA : bénéfice record", "summary": "", "published_at": None}
        ]
        assert news.store_articles(db, get_market(), items) == 2
        assert news.store_articles(db, get_market(), items) == 0  # already known
        found = news.ticker_sentiment(db, "ALPHA")
        assert found["articles"] == 2 and found["latest"][0]["title"] == "ALPHA : bénéfice record"
        assert found["score"] == round((0.6 - 0.9 * 0.8) / 1.9, 3)  # the newest article weighs 1, the one before 0.9
        assert news.ticker_sentiment(db, "ZETA")["articles"] == 0


def test_api(client):
    scored = client.post("/api/sentiment/analyze", json={"text": "ALPHA tla3et, rbe7na"}).json()
    assert scored["label"] == "positive" and scored["tickers"] == ["ALPHA"] and scored["method"] == "lexicon"
    assert client.post("/api/sentiment/analyze", json={"text": ""}).status_code == 422
    listed = client.get("/api/news").json()
    assert listed == {"scraping_enabled": False, "articles": []}
    assert client.post("/api/news/refresh").status_code == 401
    token = client.post(
        "/api/auth/register", json={"email": "n@example.com", "username": "News", "password": "long enough"}
    ).json()["access_token"]
    refused = client.post("/api/news/refresh", headers={"Authorization": f"Bearer {token}"})
    assert refused.status_code == 409 and "ENABLE_SCRAPING" in refused.json()["detail"]
