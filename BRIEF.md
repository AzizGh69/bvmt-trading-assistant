# Build brief: BVMT Trading Assistant

This file is the specification for the first build of this repository. Once the
build is done, replace it with real documentation (keep what is still true in
`docs/`).

## Goal

One working, runnable trading assistant for the Tunis Stock Exchange (BVMT),
consolidating two existing prototypes into a single coherent project owned by
Mohamed Aziz Ghazouani (GitHub `AzizGh69`), who managed the consolidated
version for an entrepreneurship competition. Licence: MIT.

## The two sources

Both are public on GitHub. Clone them outside this repository and read them
before writing anything.

| Prototype | Repository | Strongest at |
|---|---|---|
| FAIN, by team Makarouna Kadheba | `https://github.com/Moetez-Fradi/IHEC-Code-Lab-Makarouna-Kadheba` | Architecture and product: Next.js UI, FastAPI services behind a gateway, NestJS auth, PostgreSQL, Redis, LSTM forecasts, Markowitz with SHAP, RAG chatbot, Tunizi sentiment |
| Tradeili, by The Overfitters | `https://github.com/bechir23/ihec-fintech` | Statistical rigour and agents: ADF / AIC / BIC diagnostics, backtests, a 5-agent pipeline with logged hand-offs and safety rules, reinforcement learning, a 4-signal decision engine, good docs |

Licensing, which decides how each may be used:

- **FAIN's README declares the MIT licence.** Its code may be reused. Keep a
  notice naming the team and the repository (a `NOTICE` file and the README
  credits).
- **Tradeili has no licence file.** Its authors agreed to this project building
  on their work, but do not copy its files. Reimplement its ideas (the
  diagnostics, the agent pipeline, the decision engine, the reinforcement
  learning) in your own code and credit the team as the inspiration.

## What to build

Take FAIN's architecture as the base and bring Tradeili's strengths into it.
Where the two overlap, keep the better one; do not ship two of anything.

Features, in priority order. Finish and push each before starting the next, so
an interruption leaves a working repository:

1. **Market data.** Clean the 2016 to 2025/2026 BVMT price history (the files
   in the sources' `data/` folders; two formats, fixed-width `.txt` and
   semicolon `.csv`) into one tidy table. Commit the cleaned result as a
   compressed Parquet file with the script that produced it; do not commit the
   ~200 MB of raw files. Load it into PostgreSQL on first start.
2. **API and dashboard core.** Market overview (TUNINDEX, gainers and losers,
   volumes), a stock page with RSI, MACD and Bollinger Bands.
3. **Forecasting.** 5-day price and volume forecasts with confidence intervals,
   plus the diagnostics from Tradeili: ADF stationarity, AIC/BIC model
   selection, backtest RMSE and directional accuracy. Report measured numbers
   only.
4. **Anomaly detection.** Isolation Forest, volume Z-score above 3 sigma, price
   moves over 5%, alerts ranked by severity.
5. **Portfolio.** Markowitz optimisation explained with SHAP; Sharpe ratio, max
   drawdown, VaR, stress tests; a simulator; the investor profile from sign-up.
6. **Agent pipeline.** Scraper, forecast, sentiment, anomaly, recommendation,
   with the hand-offs logged and the safety rules enforced, and a page that
   shows a run.
7. **Sentiment and assistants.** News sentiment in French, Arabic and Tunizi;
   a RAG chatbot over BVMT documentation; a chat that knows the user's
   portfolio.
8. **Reinforcement learning** on the portfolio from user feedback.
9. **The rest of the product.** Email alerts, scheduled reports, light and dark
   themes.

## Constraints

- **No secrets.** Copy no `.env`, key, token or database URL from either
  source, and search the code you reuse for hard-coded ones. Configuration is
  environment variables, documented in `.env.example`.
- **It runs without any API key.** Every LLM feature goes through one
  OpenAI-compatible client set by `LLM_BASE_URL`, `LLM_API_KEY` and
  `LLM_MODEL`, so OpenAI, Groq or OpenRouter all work. With no key, sentiment
  falls back to a lexicon scorer and the chat says it is not configured.
- **Live scraping is opt-in** behind an environment flag, with timeouts and a
  soft failure. Tests never touch the network.
- **It starts with one command** (`docker compose up`), and the README also
  gives the steps without Docker.
- **Small enough for a free host.** Prefer few processes: merge thin services
  rather than keeping twelve for their own sake, and say in the README how many
  there are. Keep heavy models optional or precomputed.
- **Honest claims.** No "production ready", no invented accuracy, no live URL
  that does not exist. Add a line that this is not financial advice.

## Tests and CI

- `pytest` for the data loader, indicators, forecasting diagnostics, anomaly
  rules, the optimiser, the decision engine and the agent pipeline (LLM
  mocked).
- The frontend builds (`next build`) and lints.
- A GitHub Actions workflow runs both on every push and pull request.
- Before calling it done, start the stack, call the main endpoints and open the
  main pages.

## README

In English: what it is, features, architecture, quick start, environment
variables, tests, and a **Credits** section saying this project is inspired by
and built on two prototypes, FAIN by team Makarouna Kadheba and Tradeili by The
Overfitters, with their agreement, linking both repositories. Author: Mohamed
Aziz Ghazouani (project manager of the consolidated version). Do not credit him
with writing the original prototypes.

## Delivery

Push your branch often and open one pull request into `main`. Do not merge it,
do not change the repository's visibility, and do not deploy anything. In the
pull request body, say what works, what is partial, what was left out, the
final stack and the number of services.
