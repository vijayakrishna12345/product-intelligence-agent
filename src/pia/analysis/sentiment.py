"""VADER sentiment labels for ingested reviews."""

from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_ANALYZER = SentimentIntensityAnalyzer()


def score_text(text: str | None) -> tuple[str, float]:
    raw = (text or "").strip()
    if not raw:
        return "neutral", 0.0
    compound = float(_ANALYZER.polarity_scores(raw)["compound"])
    if compound >= 0.05:
        return "positive", compound
    if compound <= -0.05:
        return "negative", compound
    return "neutral", compound
