# BVMT Trading Assistant

A trading assistant for the Tunis Stock Exchange (BVMT), built as an educational
project: ten years of daily quotations, 5-session forecasts with their
diagnostics, anomaly surveillance, a Markowitz portfolio tested out of sample, a
paper-trading account, a five-agent pipeline with safety rules, news sentiment
in French, Arabic and Tunizi, and an assistant that knows your paper portfolio.

The interface is in French; the code and this document are in English.

> **Not financial advice.** Every figure is computed from historical prices
> that stop on 6 February 2026. Forecasts and recommendations are statistics
> with their uncertainty, not predictions to act on. No real order is ever
> placed.

## Features

| Area | What it does |
|---|---|
| **Market data** | 89 securities (77 listed at the last session), 2,531 sessions from 4 Jan 2016 to 6 Feb 2026, cleaned from about 1.5 million raw rows into one 2.9 MB Parquet file. Loaded into the database on first start. |
| **Dashboard** | Market overview (composite index, breadth, gainers, losers, most active, volumes) and a page per stock with RSI, MACD, Bollinger Bands and moving averages. The index is a liquidity-weighted **proxy** computed from share prices, not the official TUNINDEX. |
| **Forecasting** | ARIMA (order by AIC, BIC reported), a damped exponential average and the random walk compete on a walk-forward backtest of the last 120 sessions; the lowest RMSE wins. 80 % and 95 % bands, ADF stationarity tests, directional accuracy, a volume forecast. When nothing beats the random walk, the page says so. |
| **Anomalies** | Volume z-score above 3, price moves above 5 %, and an Isolation Forest on volume, move size and intraday range. Severity from low to critical; moves over 15 % are labelled corporate actions. |
| **Portfolio** | Long-only mean-variance optimisation (SLSQP) over the 40 most liquid listed stocks, Ledoit-Wolf covariance, shrunk expected returns, three risk profiles from a sign-up questionnaire. Each holding is explained by its share of expected return and its Euler share of risk. Sharpe, max drawdown, VaR and CVaR, four stress tests, and an **out-of-sample check** against equal weight. |
| **Paper trading** | An account per user with a chosen starting capital: orders at the last close, positions, P&L, the risk of the current weights, and one click to follow the recommended allocation. |
| **Agent pipeline** | Market, forecast, sentiment, anomaly and recommendation agents hand off in turn; every hand-off is stored and replayed on the Agents page. A failing agent is reported, not fatal. |
| **Decision engine** | Forecast, technical and news signals weighted into BUY / HOLD / SELL against a profile threshold. The forecast counts only when its model beat the random walk. Six safety rules (delisted, recent severe anomaly, illiquid, thin evidence, position cap, no short selling) can override the call. |
| **Learning from feedback** | A thumbs up or down on a BUY or SELL call tilts how much that user's engine trusts each signal (a bounded gradient bandit, 0.5 to 1.5). Safety rules never move. |
| **Sentiment** | The configured LLM scores a text from −1 to 1; without one, a lexicon reads French, Arabic and Tunizi (Arabizi digits, negation such as "ma tla3ch", phrases such as "baisse des bénéfices"). News comes from RSS feeds, off by default. |
| **Assistant** | TF-IDF retrieval over a French knowledge base about the BVMT and the app's own methods, answered by the LLM with your paper portfolio and the figures of any stock you name. Without an LLM it says it is not configured and shows the passages it found. |
| **Reports and alerts** | Once per session: the session's alerts, a market report, and e-mails to subscribers about their own holdings first. Without SMTP the e-mails are kept in an in-app outbox. An optional scheduler runs it inside the API process. |
| **Themes** | Light and dark. |

### What the numbers say

Two results are worth knowing before reading any screen:

- **Many stocks are hard to forecast.** On the last session, for 33 of the 77
  listed stocks no model beat "the next price is today's price" on the
  backtest; the app then shows the random walk and leaves the forecast out of
  its decisions. For the other 44 the chosen model (exponential average for 25,
  ARIMA for 19) had the lower backtest error.
- **The optimiser does not beat equal weight out of sample.** Choosing the
  weights on Feb 2024 – Feb 2025 and holding them over Feb 2025 – Feb 2026 gave
  a Sharpe ratio of 0.83 for the moderate profile, against 4.06 for holding the
  same 40 stocks in equal parts (a strong, low-volatility year for the BVMT).
  The portfolio page shows this comparison next to the flattering in-sample
  figures, and says in words which one won.

## Architecture

Three services, started by one command:

```
web  (Next.js 16, React 19, Tailwind 4, Recharts)  :3000
 └─ api  (one FastAPI process: every feature below)  :8000
     └─ db  (PostgreSQL 16; SQLite outside Docker)
```

The API is a single process on purpose; the two prototypes it builds on ran up
to a dozen services. Inside it:

```
backend/app/
  data/          cleaning rules, Parquet loader, sector map
  analytics/     market, indicators, forecasting, anomalies, portfolio,
                 decision engine, sentiment (LLM + lexicon), tunizi lexicon
  agents.py      the five-agent pipeline and its logged hand-offs
  policy.py      learning from feedback
  assistant.py   retrieval and the chat;  knowledge/  its French knowledge base
  news.py        RSS reading (opt-in);    jobs.py  daily report, e-mails, scheduler
  llm.py         one OpenAI-compatible client for every LLM feature
  account.py     the paper-trading account
  routers/       HTTP endpoints (interactive docs at /docs)
```

Prices are held in memory after start-up (about 208,000 rows); forecasts and the
anomaly scan are cached per session. Nothing heavy is downloaded at run time:
no embedding model, no deep-learning framework.

## Quick start

### With Docker

```bash
cp .env.example .env      # optional: every value has a default
docker compose up --build
```

Open <http://localhost:3000>. API documentation: <http://localhost:8000/docs>.
The first start loads the price history into PostgreSQL.

### Without Docker

Python 3.12+ and Node.js 22+.

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt        # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Without `DATABASE_URL` the API uses a local SQLite file (`bvmt.db`).

## Environment variables

All optional; see [.env.example](.env.example) for the full list with comments.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file | PostgreSQL URL; Docker sets it from `POSTGRES_*` |
| `JWT_SECRET` | random per start | Signs login tokens; set it to keep sessions across restarts |
| `CORS_ORIGINS` | `http://localhost:3000` | Origins allowed to call the API |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Where the browser reaches the API (build time) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | OpenAI URL, empty, `gpt-4o-mini` | Any OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter). Empty key: lexicon sentiment, and the assistant says it is not configured |
| `ENABLE_SCRAPING`, `NEWS_FEEDS` | `false`, three Tunisian RSS feeds | Read news feeds, with a timeout and per-feed soft failure |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | empty | Send alert e-mails; without a host they stay in the outbox |
| `ENABLE_SCHEDULER`, `SCHEDULER_INTERVAL_MINUTES` | `false`, `1440` | Run the daily job inside the API process |
| `RISK_FREE_RATE` | `0.07` | Annual rate used by the Sharpe ratio |

## Tests

```bash
cd backend && ruff check . && pytest        # 83 tests, no network, LLM mocked
cd frontend && npm run lint && npm run typecheck && npm run build
```

The backend tests cover the cleaning and loading of the data, indicators,
forecasting diagnostics and backtests, anomaly rules, the optimiser and risk
measures, accounts and paper trading, the decision engine and its safety rules,
the feedback policy, the agent pipeline (including a failing agent), sentiment
in three languages, the feeds, the assistant and the daily job. GitHub Actions
runs both halves on every push and pull request.

## Data

`data/bvmt_prices.parquet` is built by `scripts/build_dataset.py` from the
yearly BVMT quotation files (fixed-width `.txt` up to 2021, semicolon `.csv`
after) published in the data folders of the two prototypes. The raw files
(about 200 MB) are not committed; `data/bvmt_prices.report.json` records what
was read and kept. Sectors are assigned by hand in `backend/app/data/sectors.py`.

## Credits

This project is inspired by and built on two prototypes from IHEC CodeLab 2.0,
with their authors' agreement:

- **FAIN**, by team **Makarouna Kadheba**:
  <https://github.com/Moetez-Fradi/IHEC-Code-Lab-Makarouna-Kadheba>.
  The product and architecture this project starts from: the Next.js interface,
  a FastAPI backend, PostgreSQL, Markowitz with explanations, a RAG chatbot and
  Tunizi sentiment. FAIN is MIT-licensed; the UI shell and the Tunizi lexicon
  are adapted from it (see [NOTICE](NOTICE)).
- **Tradeili**, by **The Overfitters**: <https://github.com/bechir23/ihec-fintech>.
  The statistical rigour and the agents: ADF / AIC / BIC diagnostics and
  backtests, a five-agent pipeline with logged hand-offs and safety rules, a
  multi-signal decision engine and learning from feedback. Tradeili has no
  licence file, so none of its code is used; these ideas were reimplemented.

Consolidated version: **Mohamed Aziz Ghazouani**, project manager. The original
prototypes were written by their teams.

## Licence

[MIT](LICENSE). Portions adapted from FAIN keep their MIT notice in [NOTICE](NOTICE).
