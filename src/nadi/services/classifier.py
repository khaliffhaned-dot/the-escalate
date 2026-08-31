"""Malaysian NLP enrichment, 3R sensitivity classification, and geographic tagging."""

from __future__ import annotations

import re
from typing import Any

from nadi.domain.enums import Lang, PESO, Platform, SentimentLabel, ThreeRFlag
from nadi.domain.models import Sentiment, ThreeR

# 3R Keywords dictionary (BM, EN, Manglish)
_ROYALTY_KEYWORDS = [
    r"\bagong\b",
    r"\bistana\b",
    r"\bydpa\b",
    r"\bsultan\b",
    r"\braja\b",
    r"\broyal\b",
    r"\bdaulat\b",
    r"\bkerabat\b",
    r"\btengku\b",
    r"\btunku\b",
    r"\bmaharaja\b",
]

_RELIGION_KEYWORDS = [
    r"\bagama\b",
    r"\bislam\b",
    r"\bkristen\b",
    r"\bchristian\b",
    r"\bhindu\b",
    r"\bbuddha\b",
    r"\bjakim\b",
    r"\bhalal\b",
    r"\bhukuman\b",
    r"\bmurtad\b",
    r"\bkhutbah\b",
    r"\bsharia\b",
    r"\bsyariah\b",
]

_RACE_KEYWORDS = [
    r"\bmelayu\b",
    r"\bcina\b",
    r"\bchinese\b",
    r"\bindia\b",
    r"\bindian\b",
    r"\bbumiputera\b",
    r"\bkaum\b",
    r"\bperkauman\b",
    r"\bracis\b",
    r"\bracism\b",
    r"\bracial\b",
    r"\bpribumi\b",
]

_EAST_MY_LOCATIONS = {
    "Sabah": [r"\bsabah\b", r"\bkk\b", r"\bkota kinabalu\b", r"\bsandakan\b", r"\btawau\b", r"\bpenampang\b"],
    "Sarawak": [r"\bsarawak\b", r"\bkuching\b", r"\bmiri\b", r"\bsibu\b", r"\bbintulu\b", r"\bsamarahan\b"],
    "Labuan": [r"\blabuan\b"],
}

_WEST_MY_STATES = {
    "Johor": [r"\bjohor\b", r"\bjb\b", r"\bmuar\b", r"\bbatu pahat\b"],
    "Kedah": [r"\bkedah\b", r"\balor setar\b", r"\blangkawi\b", r"\bsungai petani\b"],
    "Kelantan": [r"\bkelantan\b", r"\bkota bharu\b", r"\bkb\b", r"\btumpat\b"],
    "Melaka": [r"\bmelaka\b", r"\bmalacca\b", r"\bayer keroh\b"],
    "Negeri Sembilan": [r"\bnegeri sembilan\b", r"\bseremban\b", r"\bport dickson\b"],
    "Pahang": [r"\bpahang\b", r"\bkuantan\b", r"\btemerloh\b", r"\bcameron\b"],
    "Perak": [r"\bperak\b", r"\bipoh\b", r"\btaiping\b", r"\bteluk intan\b"],
    "Perlis": [r"\bperlis\b", r"\bkangar\b"],
    "Pulau Pinang": [r"\bpenang\b", r"\bpulau pinang\b", r"\bgeorge town\b", r"\bbutterworth\b"],
    "Selangor": [r"\bselangor\b", r"\bshah alam\b", r"\bpj\b", r"\bpetaling jaya\b", r"\bklang\b", r"\bsubang\b"],
    "Terengganu": [r"\bterengganu\b", r"\bkuala terengganu\b", r"\bkemaman\b"],
    "WP Kuala Lumpur": [r"\bkl\b", r"\bkuala lumpur\b", r"\bbukit bintang\b", r"\bcheras\b", r"\bbangsar\b"],
    "WP Putrajaya": [r"\bputrajaya\b"],
}

# Positive & Negative Sentiment Lexicon
_POS_TERMS = ["hebat", "bagus", "puji", "terbaik", "tahniah", "berjaya", "sukses", "support", "mantap", "good", "great", "excellent", "win", "proud"]
_NEG_TERMS = ["boikot", "boycott", "marah", "teruk", "kecewa", "gagal", "batal", "isu", "scam", "tipu", "fail", "bad", "terrible", "disappointed", "protest"]


def classify_3r(text: str) -> ThreeR:
    """Identifies sensitive 3R flags in content."""
    lower = text.lower()
    flags: list[ThreeRFlag] = []

    if any(re.search(pat, lower) for pat in _ROYALTY_KEYWORDS):
        flags.append(ThreeRFlag.ROYALTY)
    if any(re.search(pat, lower) for pat in _RELIGION_KEYWORDS):
        flags.append(ThreeRFlag.RELIGION)
    if any(re.search(pat, lower) for pat in _RACE_KEYWORDS):
        flags.append(ThreeRFlag.RACE)

    if not flags:
        return ThreeR(flags=[], severity="none", review="clear")

    severity = "high" if ThreeRFlag.ROYALTY in flags else "medium"
    return ThreeR(flags=flags, severity=severity, review="in_review")


def detect_geography(text: str) -> tuple[str | None, bool]:
    """Detects Malaysian state and whether it relates to East Malaysia (Sabah/Sarawak/Labuan)."""
    lower = text.lower()

    # Check East Malaysia first
    for state, patterns in _EAST_MY_LOCATIONS.items():
        if any(re.search(pat, lower) for pat in patterns):
            return state, True

    # Check West Malaysia
    for state, patterns in _WEST_MY_STATES.items():
        if any(re.search(pat, lower) for pat in patterns):
            return state, False

    return None, False


def detect_language(text: str) -> Lang:
    """Heuristic language classification for Malaysian multilingual text."""
    lower = text.lower()
    bm_markers = [" yang ", " dan ", " di ", " ini ", " untuk ", " dengan ", " pada ", " kami ", " saya ", " telah "]
    en_markers = [" the ", " and ", " in ", " this ", " for ", " with ", " on ", " our ", " we ", " have "]
    
    bm_count = sum(1 for m in bm_markers if m in lower)
    en_count = sum(1 for m in en_markers if m in lower)

    # Check for Chinese characters
    if re.search(r"[\u4e00-\u9fff]", text):
        return Lang.ZH
    # Check for Tamil characters
    if re.search(r"[\u0b80-\u0bff]", text):
        return Lang.TA

    if bm_count > 0 and en_count > 0:
        return Lang.MIXED
    elif bm_count > en_count:
        return Lang.BM
    elif en_count > bm_count:
        return Lang.EN
    return Lang.EN


def analyze_sentiment(text: str) -> Sentiment:
    """Rule-based sentiment score and nuance tagger."""
    lower = text.lower()
    pos_score = sum(1 for t in _POS_TERMS if t in lower)
    neg_score = sum(1 for t in _NEG_TERMS if t in lower)

    nuances = []
    if "sme" in lower or "peniaga" in lower:
        nuances.append("sme_on_pack")
    if "sabah" in lower or "sarawak" in lower or "borneo" in lower:
        nuances.append("east_my")
    if "boikot" in lower or "boycott" in lower:
        nuances.append("boycott_call")

    if pos_score > neg_score:
        score = min(1.0, 0.3 + (pos_score * 0.2))
        return Sentiment(label=SentimentLabel.POS, score=score, nuance=nuances)
    elif neg_score > pos_score:
        score = max(-1.0, -0.3 - (neg_score * 0.2))
        return Sentiment(label=SentimentLabel.NEG, score=score, nuance=nuances)
    else:
        return Sentiment(label=SentimentLabel.NEU, score=0.0, nuance=nuances)
