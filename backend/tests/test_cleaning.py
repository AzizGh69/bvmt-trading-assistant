"""The raw-file parsers and the cleaning rules (fixtures are hand-written lines in each format)."""
from __future__ import annotations

import pandas as pd

from app.data.cleaning import (
    TIDY_COLUMNS,
    clean,
    isin_check_digit,
    legacy_code_to_isin,
    make_ticker,
    parse_file,
    parse_fixed_width,
    parse_semicolon,
    parse_web_export,
)

FIXED_2016 = """\
SEANCE      GROUPE CODE   VALEUR               OUVERTURE     CLOTURE    PLUS_BAS   PLUS_HAUT  QUANTITE_NEGOCIEE  NB_TRANSACTION          CAPITAUX IND_RES
---------- ------- ------ ------------------ ----------- ----------- ----------- ----------- ------------------ --------------- ----------------- -------
04/01/2016      11 100010 MONOPRIX                14.190      13.900      13.770      14.190               2008              21         27847.950
04/01/2016      21 900001 EMPRUNT 6% 2020        100.000     100.000     100.000     100.000                 10               1          1000.000
05/01/2016      11 100010 MONOPRIX                13.900      13.900       0.000       0.000                  0               0             0.000

2 rows selected.
""".splitlines()

FIXED_2018 = """\
SEANCE     C_GR_RLC CODE_VAL                 LIB_VAL             COURS_REF COURS_VEILLE  OUVERTURE DERNIER_COURS    CLOTURE   PLUS_BAS  PLUS_HAUT QUANTITE_NEGOCIEE    NB_TRAN   CAPITAUX I
-------- ---------- ------------------------ ------------------ ---------- ------------ ---------- ------------- ---------- ---------- ---------- ----------------- ---------- ---------- -
02/01/18         11 100010                   MONOPRIX                 11,6         11,6       11,5         11,39      11,39      11,25       11,5              2926          7    33635,5
""".splitlines()

SEMICOLON_2022 = """\
SEANCE    ;GROUPE    ;CODE        ;VALEUR          ;OUVERTURE ;CLOTURE    ;PLUS_BAS   ;PLUS_HAUT ;QUANTITE_NEGOCIEE;NB_TRANSACTION ;CAPITAUX
03/01/2022   ;11        ;TN0001000108;MONOPRIX          ;4.650     ;4.660     ;4.600     ;4.700     ;744               ;3              ;3459.600
03/01/2022   ;32        ;TN0009999999;AB DA 1/7         ;0.100     ;0.100     ;0.100     ;0.100     ;5                 ;1              ;0.500
03/01/2022   ;12        ;TN0002400505;UBCI              ;22.000    ;22.000    ;0.000     ;0.000     ;0                 ;0              ;0.000
""".splitlines()

WEB_2026 = """\
Séance,ISIN.,Val.,Ouv.,Clô.,+ haut,+ bas,CMP,Nb. Tr.,Qté,Cap.
06/01/2026,TN0001000108,MONOPRIX,0,0,0,0,0,0,0,0
05/01/2026,TN0001000108,MONOPRIX,6.1,6.2,6.25,6.05,6.15,12,500,3075.5
05/01/2026,TNNEWLISTING1,NEWCO,3,3.1,3.2,2.9,3.05,4,100,305
""".splitlines()


def test_isin_check_digit_matches_known_isins():
    assert isin_check_digit("TN000100010") == "8"  # MONOPRIX
    assert isin_check_digit("TN000110025") == "4"  # SFBT
    assert legacy_code_to_isin("100010") == "TN0001000108"
    assert legacy_code_to_isin("503001") == "TN0005030010"
    assert legacy_code_to_isin("TN0001000108") == "TN0001000108"


def test_make_ticker_is_url_safe():
    assert make_ticker("BTE (ADP)") == "BTE-ADP"
    assert make_ticker("SPDIT - SICAF") == "SPDIT-SICAF"
    assert make_ticker("Société Générale") == "SOCIETE-GENERALE"


def test_parse_fixed_width_dot_decimals():
    frame = parse_fixed_width(FIXED_2016)
    assert len(frame) == 3  # the footer and the blank line are skipped
    first = frame.iloc[0]
    assert first["date"] == pd.Timestamp("2016-01-04")
    assert first["code"] == "100010" and first["name"] == "MONOPRIX"
    assert (first["open"], first["close"], first["low"], first["high"]) == (14.19, 13.9, 13.77, 14.19)
    assert first["volume"] == 2008 and first["trades"] == 21 and first["turnover"] == 27847.95


def test_parse_fixed_width_comma_decimals_and_short_year():
    frame = parse_fixed_width(FIXED_2018)
    row = frame.iloc[0]
    assert row["date"] == pd.Timestamp("2018-01-02")
    assert row["market_group"] == 11
    assert (row["open"], row["close"], row["low"], row["high"]) == (11.5, 11.39, 11.25, 11.5)
    assert row["volume"] == 2926 and row["turnover"] == 33635.5


def test_parse_semicolon():
    frame = parse_semicolon(SEMICOLON_2022)
    assert list(frame["name"]) == ["MONOPRIX", "AB DA 1/7", "UBCI"]
    assert frame.iloc[0]["close"] == 4.66 and frame.iloc[0]["volume"] == 744


def test_parse_web_export_has_no_group():
    frame = parse_web_export(WEB_2026)
    assert len(frame) == 3
    assert frame["market_group"].isna().all()
    traded = frame[frame["volume"] > 0].iloc[0]
    assert (traded["open"], traded["close"], traded["high"], traded["low"]) == (6.1, 6.2, 6.25, 6.05)


def test_parse_file_detects_each_format(tmp_path):
    for name, lines in {"a.txt": FIXED_2016, "b.txt": FIXED_2018, "c.csv": SEMICOLON_2022, "d.csv": WEB_2026}.items():
        path = tmp_path / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert len(parse_file(path)) >= 1, name


def test_clean_unifies_identity_and_applies_rules():
    raw = pd.concat(
        [parse_fixed_width(FIXED_2016), parse_fixed_width(FIXED_2018), parse_semicolon(SEMICOLON_2022), parse_web_export(WEB_2026)],
        ignore_index=True,
    )
    tidy = clean(raw)
    assert list(tidy.columns) == TIDY_COLUMNS
    # bonds (21) and rights (32) are gone
    assert set(tidy["name"]) == {"MONOPRIX", "UBCI", "NEWCO"}
    # the legacy code and the ISIN are one security with one ticker
    monoprix = tidy[tidy["ticker"] == "MONOPRIX"].set_index("date")
    assert monoprix["isin"].nunique() == 1 and monoprix["isin"].iloc[0] == "TN0001000108"
    assert len(monoprix) == 4  # 04/01/2016, 02/01/2018, 03/01/2022, 05/01/2026
    # a session where nothing traded is dropped (05/01/2016 and 06/01/2026 had no trade at all)
    assert pd.Timestamp("2016-01-05") not in monoprix.index
    assert pd.Timestamp("2026-01-06") not in monoprix.index
    # an untraded row keeps the carried close and gets a flat bar
    ubci = tidy[tidy["ticker"] == "UBCI"].iloc[0]
    assert not ubci["traded"]
    assert ubci["open"] == ubci["high"] == ubci["low"] == ubci["close"] == 22.0
    # a security first seen in the web export defaults to the main equity group
    assert tidy[tidy["ticker"] == "NEWCO"]["market_group"].iloc[0] == 11
    # bars are consistent
    assert ((tidy["low"] <= tidy[["open", "close"]].min(axis=1)) & (tidy["high"] >= tidy[["open", "close"]].max(axis=1))).all()


def test_clean_prefers_the_traded_duplicate():
    lines = SEMICOLON_2022[:2] + [
        "03/01/2022   ;11        ;TN0001000108;MONOPRIX          ;4.650     ;4.650     ;0.000     ;0.000     ;0                 ;0              ;0.000"
    ]
    tidy = clean(parse_semicolon(lines))
    assert len(tidy) == 1
    assert tidy.iloc[0]["volume"] == 744 and tidy.iloc[0]["close"] == 4.66


def test_committed_history_is_tidy(real_prices):
    df = real_prices
    assert list(df.columns) == TIDY_COLUMNS
    assert not df.duplicated(["date", "isin"]).any()
    assert df["ticker"].nunique() == df["isin"].nunique()
    assert (df["close"] > 0).all()
    assert df["date"].min().year == 2016 and df["date"].max().year >= 2025
    assert ((df["low"] <= df["close"]) & (df["close"] <= df["high"])).all()
    assert (df.loc[~df["traded"], "volume"] == 0).all()
