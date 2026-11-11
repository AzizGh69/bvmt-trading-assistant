"""Parsers and cleaning rules for the raw BVMT daily quotation files.

The exchange's yearly exports come in four shapes:

* fixed-width text, 2016-2017 and 2020-2021 (``SEANCE GROUPE CODE VALEUR ...``,
  dot decimals, four-digit years);
* fixed-width text, 2018-2019 (``SEANCE C_GR_RLC CODE_VAL LIB_VAL ...``, comma
  decimals, two-digit years, extra reference-price columns);
* semicolon-separated ``.csv``, 2022-2025;
* a comma-separated web export for 2026 with French short headers and no
  market-group column.

Everything is normalised to one tidy table with one row per (session, security).
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

# Market groups ("GROUPE") that hold shares. The other groups are bonds (21),
# subscription / allotment rights (32, 33) and funds (71).
EQUITY_GROUPS = frozenset({11, 12, 13, 51, 52, 99})

TIDY_COLUMNS = [
    "date",
    "isin",
    "ticker",
    "name",
    "market_group",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trades",
    "turnover",
    "traded",
]

_RAW_COLUMNS = ["date", "market_group", "code", "name", "open", "close", "low", "high", "volume", "trades", "turnover"]

# Header aliases across the fixed-width and semicolon formats.
_ALIASES = {
    "SEANCE": "date",
    "GROUPE": "market_group",
    "C_GR_RLC": "market_group",
    "CODE": "code",
    "CODE_VAL": "code",
    "VALEUR": "name",
    "LIB_VAL": "name",
    "OUVERTURE": "open",
    "CLOTURE": "close",
    "PLUS_BAS": "low",
    "PLUS_HAUT": "high",
    "QUANTITE_NEGOCIEE": "volume",
    "NB_TRANSACTION": "trades",
    "NB_TRAN": "trades",
    "CAPITAUX": "turnover",
}

# Header aliases of the 2026 web export (accents stripped, lower-cased).
_WEB_ALIASES = {
    "seance": "date",
    "isin.": "code",
    "val.": "name",
    "ouv.": "open",
    "clo.": "close",
    "+ haut": "high",
    "+ bas": "low",
    "nb. tr.": "trades",
    "qte": "volume",
    "cap.": "turnover",
}

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2,4}$")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _numeric(series: pd.Series) -> pd.Series:
    """Parse numbers written with either dot or comma decimals."""
    text = series.astype(str).str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False)
    return pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")


def _dates(series: pd.Series) -> pd.Series:
    """Parse ``dd/mm/yyyy`` and ``dd/mm/yy`` session dates."""
    text = series.astype(str).str.strip()
    long_form = pd.to_datetime(text.where(text.str.len() == 10), format="%d/%m/%Y", errors="coerce")
    short_form = pd.to_datetime(text.where(text.str.len() == 8), format="%d/%m/%y", errors="coerce")
    return long_form.fillna(short_form)


def isin_check_digit(body: str) -> str:
    """Check digit of an ISIN given its first 11 characters (ISO 6166, Luhn)."""
    digits = "".join(str(int(ch, 36)) for ch in body.upper())
    total = 0
    for position, ch in enumerate(reversed(digits)):
        n = int(ch)
        if position % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - total % 10) % 10)


def legacy_code_to_isin(code: str) -> str:
    """Map a pre-2021 six-digit BVMT code to its ISIN.

    Tunisian ISINs for securities listed before 2021 are ``TN000`` followed by
    the legacy six-digit code and the ISO 6166 check digit, e.g. ``100010`` ->
    ``TN0001000108``. Codes that are already ISINs are returned unchanged.
    """
    code = code.strip().upper()
    if len(code) == 12 and code[:2].isalpha():
        return code
    if code.isdigit() and len(code) <= 6:
        body = "TN000" + code.zfill(6)
        return body + isin_check_digit(body)
    return code


def make_ticker(name: str) -> str:
    """URL-safe identifier derived from the security's display name."""
    slug = _strip_accents(name).upper()
    slug = re.sub(r"[^A-Z0-9]+", "-", slug).strip("-")
    return slug or "UNKNOWN"


def _spans(dash_line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"-+", dash_line)]


def parse_fixed_width(lines: Iterable[str]) -> pd.DataFrame:
    """Parse one of the fixed-width ``histo_cotation_*.txt`` exports."""
    lines = list(lines)
    header_idx = next(i for i, ln in enumerate(lines) if ln.lstrip().upper().startswith("SEANCE"))
    header, dashes = lines[header_idx], lines[header_idx + 1]
    spans = _spans(dashes)
    names = []
    for start, end in spans:
        raw = header[start:end].strip() or header[start : end + 4].strip()
        names.append(_ALIASES.get(raw.split()[0] if raw else "", None))
    # The last data column of a span can overflow to the left (right-aligned
    # numbers wider than the heading), so cut at the midpoints between spans.
    bounds = [0] + [spans[i + 1][0] - 1 for i in range(len(spans) - 1)] + [None]
    records = []
    for line in lines[header_idx + 2 :]:
        if not _DATE_RE.match(line[:10].strip()):
            continue  # blank lines, repeated headers, footers
        row = {}
        for idx, key in enumerate(names):
            if key is None:
                continue
            row[key] = line[bounds[idx] : bounds[idx + 1]].strip()
        records.append(row)
    return _finalise(pd.DataFrame.from_records(records))


def parse_semicolon(lines: Iterable[str]) -> pd.DataFrame:
    """Parse one of the semicolon-separated ``histo_cotation_*.csv`` exports."""
    iterator = iter(lines)
    header = [_ALIASES.get(col.strip().upper()) for col in next(iterator).split(";")]
    records = []
    for line in iterator:
        parts = line.rstrip("\r\n").split(";")
        if len(parts) < len(header) or not _DATE_RE.match(parts[0].strip()):
            continue
        records.append({key: parts[i].strip() for i, key in enumerate(header) if key})
    return _finalise(pd.DataFrame.from_records(records))


def parse_web_export(lines: Iterable[str]) -> pd.DataFrame:
    """Parse the comma-separated web export (2026), which has no group column."""
    reader = csv.reader(lines)
    header = [_WEB_ALIASES.get(_strip_accents(col).strip().lower()) for col in next(reader)]
    records = []
    for parts in reader:
        if len(parts) < len(header) or not _DATE_RE.match(parts[0].strip()):
            continue
        records.append({key: parts[i].strip() for i, key in enumerate(header) if key})
    frame = pd.DataFrame.from_records(records)
    frame["market_group"] = ""
    return _finalise(frame)


def _finalise(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_RAW_COLUMNS)
    out = pd.DataFrame(index=frame.index)
    out["date"] = _dates(frame["date"])
    out["market_group"] = pd.to_numeric(frame["market_group"], errors="coerce")
    out["code"] = frame["code"].astype(str).str.strip()
    out["name"] = frame["name"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    for col in ("open", "close", "low", "high", "volume", "trades", "turnover"):
        out[col] = _numeric(frame[col])
    return out.dropna(subset=["date"])[_RAW_COLUMNS]


def parse_file(path: Path) -> pd.DataFrame:
    """Detect the format of a raw file and parse it."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.strip()), "")
    if ";" in first:
        return parse_semicolon(lines)
    if "," in first and first.count(",") >= 8:
        return parse_web_export(lines)
    return parse_fixed_width(lines)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn concatenated parser output into the tidy equity price table.

    Rules, in order:

    1. legacy six-digit codes become ISINs, so a security keeps one identity
       across the 2021 change of code scheme;
    2. rows without a market group (the web export) inherit the security's most
       recent known group; securities never seen with a group are assumed to be
       ordinary shares (group 11) because the web export only lists shares;
    3. only equity groups are kept (no bonds, rights or funds);
    4. duplicate (session, security) rows (overlapping yearly files) collapse to
       one, preferring the row that shows trading;
    5. a session without trades carries the previous close: the exchange
       repeats the reference price with zero high / low / volume, and the web
       export writes zeros everywhere. Such rows get ``traded = False`` and a
       flat open = high = low = close; leading rows with no price are dropped;
    6. traded rows with a missing or zero open / high / low fall back to the
       close, and high / low are widened so that low <= open, close <= high;
    7. sessions on which no security traded at all (market holidays that the
       exports still list) are removed.
    """
    df = raw.copy()
    df["isin"] = df["code"].map(legacy_code_to_isin)
    df = df.sort_values(["isin", "date"], kind="stable")

    known_group = df.groupby("isin")["market_group"].transform(lambda s: s.ffill().bfill())
    df["market_group"] = df["market_group"].fillna(known_group).fillna(11).astype(int)
    df = df[df["market_group"].isin(EQUITY_GROUPS)]

    for col in ("volume", "trades", "turnover"):
        df[col] = df[col].fillna(0).clip(lower=0)
    df["traded"] = df["volume"] > 0
    df = (
        df.sort_values(["isin", "date", "traded", "turnover"], kind="stable")
        .drop_duplicates(["isin", "date"], keep="last")
        .reset_index(drop=True)
    )

    for col in ("open", "high", "low", "close"):
        df[col] = df[col].where(df[col] > 0)
    df["close"] = df.groupby("isin")["close"].ffill()
    df = df.dropna(subset=["close"])
    for col in ("open", "high", "low"):
        df[col] = df[col].where(df["traded"]).fillna(df["close"])
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)

    open_sessions = df.groupby("date")["traded"].transform("any")
    df = df[open_sessions]

    # One display name and ticker per security: the most recent name wins.
    latest_name = df.groupby("isin")["name"].last()
    tickers = latest_name.map(make_ticker)
    duplicated = tickers[tickers.duplicated(keep=False)]
    for isin in duplicated.index:  # two securities sharing a name: disambiguate
        tickers.loc[isin] = f"{tickers.loc[isin]}-{isin[-4:]}"
    df["name"] = df["isin"].map(latest_name)
    df["ticker"] = df["isin"].map(tickers)

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["volume"] = df["volume"].round().astype("int64")
    df["trades"] = df["trades"].round().astype("int32")
    df["market_group"] = df["market_group"].astype("int16")
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].round(3)
    df["turnover"] = df["turnover"].round(3)
    return df.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)[TIDY_COLUMNS]
