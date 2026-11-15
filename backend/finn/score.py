"""Materiality = category weight × relevance × surprise × your boost  →  S/A/B/C tier.

The weight table *is* the per-category judgment from the design doc (Push 2): with relevance 1.0
and no surprise, each category lands on its default tier; subtypes move it up or down.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config

# (category, subtype) -> weight. "" subtype is the category default.
WEIGHTS: dict[tuple[str, str], float] = {
    ("results", ""): 0.90,
    ("management_change", "top"): 0.85,
    ("management_change", "other"): 0.40,
    ("management_change", "independent"): 0.30,
    ("management_change", ""): 0.40,
    ("credit_rating", "downgrade"): 0.90,
    ("credit_rating", "upgrade"): 0.55,
    ("credit_rating", "reaffirm"): 0.30,
    ("credit_rating", ""): 0.30,
    ("M&A", ""): 0.60,
    ("pledging", ""): 0.60,
    ("litigation", "regulator"): 0.85,
    ("litigation", ""): 0.55,
    ("fund_raise", ""): 0.55,
    ("insider_trading", "promoter"): 0.55,
    ("insider_trading", ""): 0.10,
    ("capex", ""): 0.35,
    ("press_release", "order_win"): 0.40,
    ("press_release", ""): 0.30,
    ("dividend", ""): 0.30,
    ("bonus_split", ""): 0.30,
    ("earnings_call", ""): 0.15,
    ("board_meeting", ""): 0.12,
    ("investor_meetings", ""): 0.05,
    ("agm_egm", ""): 0.05,
    ("postal_ballot", ""): 0.05,
    ("routine", ""): 0.05,
    ("unclassified", ""): 0.08,
}


def category_weight(category: str, sub: str) -> float:
    return WEIGHTS.get((category, sub)) or WEIGHTS.get((category, ""), 0.08)


@dataclass
class Portfolio:
    holdings: dict[str, dict] = field(default_factory=dict)  # ticker -> {sector, weight, starred}
    starred_categories: set[str] = field(default_factory=set)

    @property
    def sectors(self) -> set[str]:
        return {h["sector"] for h in self.holdings.values() if h.get("sector")}


def relevance(ticker: str, sector: str, pf: Portfolio) -> tuple[float, str]:
    h = pf.holdings.get(ticker)
    if h:
        return 1.0 + float(h.get("weight", 0.0)), "your holding"
    if sector and sector in pf.sectors:
        return 0.5, f"{sector} peer"
    return 0.2, "outside portfolio"


def surprise(category: str, card: dict, price_move: dict) -> tuple[float, str]:
    """>1 when the content is unexpected. Uses whatever the enrichment step found."""
    s, why = 1.0, ""
    if category == "results":
        yoy = (card.get("pat") or {}).get("yoy_pct")
        if yoy is not None and abs(yoy) >= 20:
            s, why = 1.15, f"PAT {yoy:+.0f}% YoY"
    if category == "pledging":
        dp = card.get("pledge_change_pp")
        if dp is not None and dp > 5:
            s, why = 1.5, f"pledge +{dp:.1f} pp"
    if category == "M&A":
        pct = card.get("deal_pct_mcap")
        if pct is not None and pct >= 10:
            s, why = 1.4, f"deal {pct:.0f}% of market cap"
    if category == "press_release":
        pct = card.get("order_pct_revenue")
        if pct is not None and pct >= 10:
            s, why = 1.4, f"order {pct:.0f}% of revenue"
    if category == "insider_trading":
        val = card.get("value_cr")
        if val is not None and val < 1:
            s, why = 0.2, "under ₹1 cr"
    pm = (price_move or {}).get("pct")
    if pm is not None and abs(pm) >= config.DEFAULT_PRICE_PCT:
        s *= 1.2
        why = (why + "; " if why else "") + f"stock {pm:+.1f}% same day"
    return s, why


def tier_for(score: float) -> str:
    if score >= config.TIER_S:
        return "S"
    if score >= config.TIER_A:
        return "A"
    if score >= config.TIER_B:
        return "B"
    return "C"


CATEGORY_LABEL = {
    "results": "Results", "management_change": "Management change", "credit_rating": "Credit rating",
    "M&A": "M&A", "pledging": "Pledge", "litigation": "Litigation", "fund_raise": "Fund raise",
    "insider_trading": "Insider trade", "capex": "Capex", "press_release": "Press release",
    "dividend": "Dividend", "bonus_split": "Bonus / split", "earnings_call": "Concall",
    "board_meeting": "Board meeting", "investor_meetings": "Investor meet", "agm_egm": "AGM / EGM",
    "postal_ballot": "Postal ballot", "routine": "Routine", "unclassified": "Other",
}


def score_filing(ticker: str, sector: str, category: str, sub: str, card: dict, price_move: dict,
                 pf: Portfolio) -> tuple[float, str, dict]:
    w = category_weight(category, sub)
    rel, rel_why = relevance(ticker, sector, pf)
    sur, sur_why = surprise(category, card or {}, price_move or {})
    boost, boost_why = 1.0, ""
    if category in pf.starred_categories or (pf.holdings.get(ticker) or {}).get("starred"):
        boost, boost_why = 1.25, "you starred this"
    score = min(1.0, w * rel * sur * boost)
    t = tier_for(score)
    contributions = [
        (w, f"{CATEGORY_LABEL.get(category, category)}{' (' + sub + ')' if sub else ''}"),
        (rel, rel_why),
        (sur, sur_why),
        (boost, boost_why),
    ]
    # "why S?" chip: top two factors by how much they lift (or are) the score
    top = [why for val, why in sorted(contributions, key=lambda x: -x[0]) if why][:2]
    factors = {"weight": w, "relevance": rel, "surprise": sur, "boost": boost, "why": top}
    return round(score, 3), t, factors
