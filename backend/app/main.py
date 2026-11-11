"""FastAPI application: one process serving every backend feature."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .analytics.market import MarketData, get_market, set_market
from .config import get_settings
from .data.loader import bootstrap_prices, load_price_frame
from .db import get_engine, init_db
from .routers import agents, anomalies, auth, forecast, market, portfolio, sentiment

log = logging.getLogger("bvmt")

DISCLAIMER = "Educational project. Nothing here is financial advice."


def load_market() -> MarketData:
    """Create tables, load the Parquet history on first start and cache prices in memory."""
    settings = get_settings()
    init_db()
    engine = get_engine()
    bootstrap_prices(engine, settings.data_parquet)
    data = MarketData(load_price_frame(engine))
    set_market(data)
    return data


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    data = load_market()
    if data.empty:
        log.warning("no price data loaded")
    else:
        log.info("market data ready: %d rows, last session %s", len(data.prices), data.last_session.date())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BVMT Trading Assistant API",
        description=f"Market data, forecasts, anomaly detection, portfolio tools and agents for the Tunis Stock Exchange. {DISCLAIMER}",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        try:
            data = get_market()
            loaded = {"rows": int(len(data.prices)), "last_session": data.last_session.date().isoformat()}
        except Exception:  # not loaded or empty
            loaded = {"rows": 0, "last_session": None}
        return {"status": "ok", "llm_configured": settings.llm_configured, "scraping_enabled": settings.enable_scraping, **loaded}

    app.include_router(market.router)
    app.include_router(forecast.router)
    app.include_router(anomalies.router)
    app.include_router(auth.router)
    app.include_router(portfolio.router)
    app.include_router(sentiment.router)
    app.include_router(agents.router)
    return app


app = create_app()
