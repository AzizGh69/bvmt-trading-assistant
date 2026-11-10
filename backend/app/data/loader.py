"""First-start bootstrap: load the committed Parquet history into the database."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from ..models import Price, Stock
from .sectors import sector_of

log = logging.getLogger(__name__)

PRICE_COLUMNS = ["stock_id", "date", "open", "high", "low", "close", "volume", "trades", "turnover", "traded"]


def read_parquet(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def bootstrap_prices(engine: Engine, parquet_path: Path) -> int:
    """Insert stocks and prices when the price table is empty. Returns rows inserted."""
    with engine.connect() as conn:
        existing = conn.execute(select(func.count()).select_from(Price)).scalar_one()
    if existing:
        return 0
    if not Path(parquet_path).exists():
        log.warning("price history %s not found; starting with an empty database", parquet_path)
        return 0

    frame = read_parquet(parquet_path)
    latest = frame.sort_values("date").groupby("isin").tail(1)
    stocks = [
        {
            "isin": row.isin,
            "ticker": row.ticker,
            "name": row.name,
            "market_group": int(row.market_group),
            "sector": sector_of(row.ticker),
        }
        for row in latest.sort_values("ticker").itertuples(index=False)
    ]
    with engine.begin() as conn:
        if not conn.execute(select(func.count()).select_from(Stock)).scalar_one():
            conn.execute(insert(Stock), stocks)
        ids = dict(conn.execute(select(Stock.isin, Stock.id)).all())

    frame["stock_id"] = frame["isin"].map(ids)
    rows = frame[PRICE_COLUMNS].copy()
    rows["date"] = rows["date"].dt.date
    if engine.dialect.name == "postgresql":
        _copy_postgres(engine, rows)
    else:
        records = rows.to_dict("records")
        with engine.begin() as conn:
            for start in range(0, len(records), 2000):
                conn.execute(insert(Price), records[start : start + 2000])
    log.info("loaded %d price rows for %d securities from %s", len(rows), len(stocks), parquet_path)
    return len(rows)


def _copy_postgres(engine: Engine, rows: pd.DataFrame) -> None:
    """Bulk-load with COPY (about a second for the full history)."""
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            statement = f"COPY prices ({', '.join(PRICE_COLUMNS)}) FROM STDIN"
            with cursor.copy(statement) as copy:
                for record in rows.itertuples(index=False, name=None):
                    copy.write_row(
                        (
                            int(record[0]), record[1], float(record[2]), float(record[3]), float(record[4]),
                            float(record[5]), int(record[6]), int(record[7]), float(record[8]), bool(record[9]),
                        )
                    )
        raw.commit()
    finally:
        raw.close()


def load_price_frame(engine: Engine) -> pd.DataFrame:
    """Read the whole price table joined with stock metadata."""
    query = (
        select(
            Price.date, Stock.isin, Stock.ticker, Stock.name, Stock.sector, Stock.market_group,
            Price.open, Price.high, Price.low, Price.close, Price.volume, Price.trades, Price.turnover, Price.traded,
        )
        .join(Stock, Stock.id == Price.stock_id)
        .order_by(Stock.ticker, Price.date)
    )
    with engine.connect() as conn:
        frame = pd.read_sql(query, conn)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["traded"] = frame["traded"].astype(bool)
    return frame
