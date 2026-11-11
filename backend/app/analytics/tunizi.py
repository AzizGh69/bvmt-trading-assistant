"""Lexicon sentiment for French, Arabic and Tunizi (Tunisian Arabic in Latin script).

The Arabizi digit table, the Tunizi market slang and the idea of mapping
company nicknames to tickers are adapted from FAIN's sentiment-analysis service
(MIT licence, team Makarouna Kadheba; see NOTICE). The matching is rewritten:
words are matched as whole tokens, longest phrase first, so "bech ti7" is not
also counted as "ti7"; Arabizi digits are only read as letters inside words,
so prices and dates are left alone; and a negation in front of a word flips it.

This is the fallback when no LLM is configured, and it is deliberately simple:
it reads market vocabulary, not irony or context.
"""
from __future__ import annotations

import re
import unicodedata

# Arabizi: digits standing for Arabic letters, read only inside a word.
ARABIZI = {"2": "a", "3": "a", "5": "kh", "6": "t", "7": "h", "8": "gh", "9": "q"}

TUNIZI = {
    # rising, winning, good
    "tla3": 0.7, "tla3et": 0.7, "tal3a": 0.6, "ti6la3": 0.6, "bech tetla3": 0.6,
    "rbe7": 0.8, "rbe7t": 0.8, "rbe7na": 0.9, "rbi7na": 0.9, "marbou7": 0.6,
    "behi": 0.5, "behya": 0.5, "mezyen": 0.5, "mezyena": 0.5, "wa3er": 0.7, "fa5er": 0.6,
    # falling, losing, bad
    "ta7": -0.7, "ta7et": -0.7, "taya7": -0.7, "tay7a": -0.7, "ti7": -0.7, "bech ti7": -0.7,
    "khsar": -0.9, "5sar": -0.9, "khsart": -0.8, "5sart": -0.8, "khsarna": -0.9, "5sarna": -0.9,
    "khayeb": -0.6, "5ayeb": -0.6, "msiba": -0.8, "cata": -0.9, "marbou6a": -0.6, "koulech marbou6": -0.8,
}

FRENCH = {
    # positive
    "hausse": 0.6, "en hausse": 0.6, "progresse": 0.6, "progression": 0.5, "grimpe": 0.6, "bondit": 0.7,
    "rebond": 0.5, "rebondit": 0.5, "record": 0.6, "benefice": 0.6, "benefices": 0.6, "beneficiaire": 0.5,
    "croissance": 0.5, "dividende": 0.5, "dividendes": 0.5, "amelioration": 0.5, "ameliore": 0.5,
    "solide": 0.4, "gain": 0.5, "gains": 0.5, "optimisme": 0.5, "optimiste": 0.5, "excedent": 0.5,
    "surperforme": 0.6, "partenariat": 0.3, "acquisition": 0.3, "redressement des resultats": 0.5,
    # negative
    "baisse": -0.6, "en baisse": -0.6, "recul": -0.6, "recule": -0.6, "chute": -0.8, "plonge": -0.8,
    "degringole": -0.8, "perte": -0.7, "pertes": -0.7, "deficit": -0.7, "deficitaire": -0.7, "declin": -0.6,
    "degradation": -0.6, "degrade": -0.6, "greve": -0.8, "faillite": -1.0, "liquidation": -0.9,
    "redressement fiscal": -0.7, "suspension": -0.6, "suspendu": -0.6, "sanction": -0.7, "amende": -0.6,
    "endettement": -0.4, "ralentissement": -0.5, "inquietude": -0.5, "pessimisme": -0.5, "crise": -0.6,
    "licenciement": -0.7, "licenciements": -0.7, "profit warning": -0.8, "avertissement sur resultats": -0.8,
}

ARABIC = {
    # positive
    "ارتفاع": 0.6, "ارتفع": 0.6, "صعود": 0.6, "أرباح": 0.7, "ارباح": 0.7, "ربح": 0.6, "نمو": 0.5,
    "تحسن": 0.5, "قياسي": 0.6, "توزيع الأرباح": 0.5,
    # negative
    "انخفاض": -0.6, "انخفض": -0.6, "تراجع": -0.6, "هبوط": -0.7, "خسائر": -0.8, "خسارة": -0.8,
    "عجز": -0.7, "إضراب": -0.8, "اضراب": -0.8, "إفلاس": -1.0, "افلاس": -1.0, "أزمة": -0.6, "ازمة": -0.6,
    "تباطؤ": -0.5,
}

NEGATIONS = {"pas", "ne", "non", "jamais", "sans", "aucun", "aucune", "mich", "mech", "moch", "موش", "لا", "ما", "لم", "لن", "غير"}

# Names people use for listed companies, mapped to the tickers of this dataset.
NICKNAMES = {
    "la biere": "SFBT", "biere": "SFBT", "celtia": "SFBT",
    "delice": "DELICE-HOLDING", "danone": "DELICE-HOLDING",
    "la banque verte": "BNA", "banque nationale agricole": "BNA",
    "amen": "AMEN-BANK", "attijari": "ATTIJARI-BANK", "wifack": "WIFACK-INT-BANK",
    "poulina": "POULINA-GP-HOLDING", "telnet": "TELNET-HOLDING", "one tech": "ONE-TECH-HOLDING",
    "carthage cement": "CARTHAGE-CEMENT", "ciments de bizerte": "CIMENTS-DE-BIZERTE",
    "ennakl": "ENNAKL-AUTOMOBILES", "tunisie leasing": "TUNISIE-LEASING-F", "air liquide": "AIR-LIQUIDE-TSIE",
    "land'or": "LAND-OR", "landor": "LAND-OR", "monoprix": "MONOPRIX", "tunisair": "TUNISAIR",
    "sotetel": "SOTETEL", "euro-cycles": "EURO-CYCLES", "eurocycles": "EURO-CYCLES",
}

LEXICON: dict[str, float] = {}
_TOKEN = re.compile(r"[\w']+", re.UNICODE)


def _fold(text: str) -> str:
    """Lower-case and strip accents and Arabic vowel marks."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _arabizi(token: str) -> str:
    if token.isdigit() or not any(ch.isdigit() for ch in token):
        return token
    return "".join(ARABIZI.get(ch, ch) for ch in token)


def tokens(text: str) -> list[str]:
    return [_arabizi(t) for t in _TOKEN.findall(_fold(text))]


def _key(phrase: str) -> str:
    return " ".join(tokens(phrase))


for _table in (TUNIZI, FRENCH, ARABIC):
    for _phrase, _weight in _table.items():
        LEXICON[_key(_phrase)] = _weight
_LONGEST = max(len(k.split()) for k in LEXICON)
_NICKNAMES = {_key(k): v for k, v in NICKNAMES.items()}
_SLANG = {_key(k) for k in TUNIZI}


def detect_language(text: str) -> str:
    """'ar' for Arabic script, 'tunizi' for Latin text with Arabizi or Tunizi words, else 'fr'."""
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    raw = _TOKEN.findall(text.lower())
    arabizi = any(re.search(r"[a-z][2-9]|[2-9][a-z]", t) for t in raw)
    folded = tokens(text)
    slang = any(" ".join(folded[i : i + n]) in _SLANG for n in (1, 2) for i in range(len(folded)))
    return "tunizi" if arabizi or slang else "fr"


def lexicon_sentiment(text: str) -> dict:
    """Score a text in [-1, 1] from the words it contains, with what matched."""
    words = tokens(text)
    matches: list[dict] = []
    i = 0
    while i < len(words):
        for n in range(min(_LONGEST, len(words) - i), 0, -1):
            phrase = " ".join(words[i : i + n])
            weight = LEXICON.get(phrase)
            negated = False
            if weight is None and n == 1:
                if phrase.startswith("ال") and len(phrase) > 4:
                    weight = LEXICON.get(phrase[2:])  # the Arabic article: "الأرباح" is "أرباح"
                elif phrase.endswith("ch") and LEXICON.get(phrase[:-2]) is not None:
                    # Tunisian "ma tla3ch": the verb carries the negation as a "-ch" suffix.
                    weight, negated = LEXICON[phrase[:-2]], True
            if weight is None:
                continue
            if not negated and any(w in NEGATIONS for w in words[max(0, i - 2) : i]):
                negated = True
            matches.append({"term": phrase, "weight": -weight if negated else weight, "negated": negated})
            i += n
            break
        else:
            i += 1
    score = sum(m["weight"] for m in matches) / len(matches) if matches else 0.0
    return {
        "score": round(max(-1.0, min(1.0, score)), 3),
        "label": label_for(score),
        "matches": matches,
        "language": detect_language(text),
    }


def label_for(score: float) -> str:
    return "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"


def nickname_tickers(text: str) -> set[str]:
    """Tickers named by a nickname ("la bière" -> SFBT)."""
    folded = " ".join(tokens(text))
    return {ticker for name, ticker in _NICKNAMES.items() if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", folded)}
