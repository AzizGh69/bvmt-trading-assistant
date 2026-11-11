"""Indicative sector labels for BVMT-listed shares.

The price files carry no sector, so this map was curated by hand for this
project. It is a convenience for grouping and diversification rules, not the
exchange's official classification.
"""
from __future__ import annotations

_SECTORS: dict[str, list[str]] = {
    "Banks": [
        "AMEN-BANK", "ATB", "ATTIJARI-BANK", "BH-BANK", "BIAT", "BNA", "BT", "BTE-ADP", "STB", "UBCI", "UIB",
        "WIFACK-INT-BANK",
    ],
    "Leasing": [
        "ATL", "ATTIJARI-LEASING", "BEST-LEASE", "BH-LEASING", "CIL", "HANNIBAL-LEASE", "TUNISIE-LEASING-F",
    ],
    "Insurance": [
        "ASSU-MAGHREBIA-VIE", "ASSUR-MAGHREBIA", "ASTREE", "BH-ASSURANCE", "BNA-ASSURANCES", "STAR", "TUNIS-RE",
    ],
    "Financial services": ["PLAC-TSIE-SICAF", "SPDIT-SICAF", "TUNINVEST-SICAR", "TUNISIE-VALEURS"],
    "Holdings": ["POULINA-GP-HOLDING"],
    "Food & beverages": [
        "SFBT", "DELICE-HOLDING", "LAND-OR", "CEREALIS", "ELBENE-INDUSTRIE", "STE-TUN-DU-SUCRE", "SOPAT",
    ],
    "Consumer goods": [
        "SAH", "NEW-BODY-LINE", "ELECTROSTAR", "ATELIER-MEUBLE-INT", "OFFICEPLAST", "EURO-CYCLES", "SITEX",
    ],
    "Automotive": [
        "ARTES", "CITY-CARS", "ENNAKL-AUTOMOBILES", "UADH", "STA", "ASSAD", "GIF-FILTER", "STIP", "STEQ",
    ],
    "Retail & distribution": ["MONOPRIX", "MAGASIN-GENERAL", "SOTUMAG", "CELLCOM", "SMART-TUNISIE"],
    "Health": ["ADWYA", "SIPHAT", "UNIMED"],
    "Building materials": [
        "CARTHAGE-CEMENT", "CIMENTS-DE-BIZERTE", "SOMOCER", "SOTEMAIL", "SANIMED", "MPBS", "TPR",
    ],
    "Real estate": ["SITS", "ESSOUKNA", "SIMPAR"],
    "Industry & chemicals": [
        "AIR-LIQUIDE-TSIE", "ALKIMIA", "ICF", "SOTUVER", "SOTIPAPIER", "SIAME", "ONE-TECH-HOLDING", "AMS",
        "SOTRAPIL",
    ],
    "Technology & telecom": [
        "TELNET-HOLDING", "SOTETEL", "AETECH", "HEXABYTE", "SERVICOM", "TAWASOL-GP-HOLDING", "MAGHREB-INTERN-PUB",
    ],
    "Transport": ["TUNISAIR"],
}

SECTOR_BY_TICKER: dict[str, str] = {ticker: sector for sector, tickers in _SECTORS.items() for ticker in tickers}


def sector_of(ticker: str) -> str:
    return SECTOR_BY_TICKER.get(ticker, "Other")
