#!/usr/bin/env python3
"""Build ``data/bvmt_prices.parquet`` from the raw BVMT quotation files.

The raw yearly files (about 200 MB, ``histo_cotation_*.txt`` / ``*.csv``) are
not committed. They are published in the ``data/`` folders of the two source
prototypes (see the README credits). Point this script at a folder holding
them:

    python scripts/build_dataset.py --raw /path/to/raw/data

It parses every file, applies the cleaning rules documented in
``backend/app/data/cleaning.py`` and writes one zstd-compressed Parquet file
plus a small JSON report of what was read and kept.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data.cleaning import clean, parse_file  # noqa: E402


def build(raw_dirs: list[Path], out: Path) -> dict:
    files = sorted({p for d in raw_dirs for p in d.iterdir() if p.suffix.lower() in {".txt", ".csv"}})
    if not files:
        raise SystemExit(f"no .txt / .csv files found in {[str(d) for d in raw_dirs]}")
    frames, per_file = [], {}
    for path in files:
        frame = parse_file(path)
        per_file[path.name] = int(len(frame))
        frames.append(frame)
        print(f"  parsed {path.name:<32} {len(frame):>8} rows")
    raw = pd.concat(frames, ignore_index=True)
    tidy = clean(raw)
    out.parent.mkdir(parents=True, exist_ok=True)
    tidy.to_parquet(out, compression="zstd", compression_level=19, index=False)
    report = {
        "raw_files": per_file,
        "raw_rows": int(len(raw)),
        "tidy_rows": int(len(tidy)),
        "securities": int(tidy["isin"].nunique()),
        "sessions": int(tidy["date"].nunique()),
        "first_session": str(tidy["date"].min().date()),
        "last_session": str(tidy["date"].max().date()),
        "traded_rows": int(tidy["traded"].sum()),
        "parquet_bytes": out.stat().st_size,
    }
    out.with_suffix(".report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, action="append", required=True, help="folder with the raw files (repeatable)")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "bvmt_prices.parquet")
    args = parser.parse_args()
    report = build(args.raw, args.out)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
