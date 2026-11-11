"""Retrieval over the knowledge base and the assistant chat (LLM mocked)."""
from __future__ import annotations

from app import assistant, llm


def test_every_section_is_loaded():
    sections = assistant.load_sections()
    assert len(sections) >= 10 and all(s.text for s in sections)


def test_retrieval_finds_the_right_section():
    index = assistant.get_index()
    assert index.search("Comment est calculée la VaR ?")[0]["title"].startswith("Les mesures de risque")
    assert index.search("c'est quoi le RSI")[0]["title"].startswith("Les indicateurs techniques")
    assert index.search("pourquoi le portefeuille optimisé fait moins bien que les parts égales")[0]["title"].startswith("Le test hors échantillon")
    assert index.search("tla3ch 3la arabizi")[0]["title"].startswith("Le sentiment")
    assert index.search("xyzzy plugh") == []


def test_chat_without_a_key_says_so_and_still_finds_documents(client):
    reply = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Qu'est-ce que la VaR ?"}]}).json()
    assert reply["configured"] is False and reply["answer"] is None
    assert reply["sources"] and reply["excerpts"] and reply["portfolio"] is False
    assert client.get("/api/assistant/status").json() == {"configured": False, "model": None}
    assert client.post("/api/assistant/chat", json={"messages": []}).status_code == 422


def test_chat_sees_the_portfolio_and_the_stocks_named(client, monkeypatch):
    seen = {}

    def fake_chat(messages, **kwargs):
        seen["context"] = messages[1]["content"]
        return "Réponse."

    monkeypatch.setattr(llm, "chat", fake_chat)
    token = client.post(
        "/api/auth/register", json={"email": "c@example.com", "username": "Chat", "password": "long enough"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/portfolio/orders", headers=headers, json={"ticker": "ALPHA", "side": "BUY", "quantity": 10})
    reply = client.post(
        "/api/assistant/chat", headers=headers, json={"messages": [{"role": "user", "content": "Que pensez-vous de BETA pour mon portefeuille ?"}]}
    ).json()
    assert reply == {**reply, "configured": True, "answer": "Réponse.", "tickers": ["BETA"], "portfolio": True}
    assert "ALPHA" in seen["context"] and "10 titres" in seen["context"]  # the position
    assert "BETA : clôture" in seen["context"]  # the stock asked about
    assert "DOCUMENTATION" in seen["context"]


def test_chat_reports_a_failing_model(client, monkeypatch):
    def failing(messages, **kwargs):
        raise llm.LLMError("the language model did not answer (ReadTimeout)")

    monkeypatch.setattr(llm, "chat", failing)
    reply = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "RSI ?"}]}).json()
    assert reply["configured"] is True and reply["answer"] is None and "ReadTimeout" in reply["error"]
