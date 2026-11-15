"""Filing category from NSE's subject line + attachment text. Keyword rules first; only filings the
rules can't place go to a small model (and only if a key is set)."""
from __future__ import annotations

import re

CATEGORIES = [
    "results", "management_change", "credit_rating", "M&A", "pledging", "litigation", "fund_raise",
    "insider_trading", "capex", "press_release", "dividend", "bonus_split", "earnings_call",
    "investor_meetings", "agm_egm", "postal_ballot", "board_meeting", "routine", "unclassified",
]

# (category, patterns on subject, patterns on text) — first match wins, order matters.
_RULES: list[tuple[str, list[str], list[str]]] = [
    ("routine", [r"trading window", r"newspaper publication", r"74\s*\(5\)", r"loss of share",
                 r"duplicate share", r"certificate under", r"compliance certificate", r"shareholding pattern",
                 r"statement of investor complaints", r"book closure", r"record date"], []),
    ("earnings_call", [r"con\.? ?call", r"conference call", r"analysts?/institutional investor meet"],
     [r"transcript", r"audio recording"]),
    ("investor_meetings", [r"analysts?/institutional investor meet", r"investor meet", r"con\.? ?call",
                            r"investor presentation", r"earnings call"], []),
    ("results", [r"financial results?", r"\bresults?\b(?! of postal)", r"integrated filing.*financ"], []),
    ("board_meeting", [r"board meeting intimation", r"prior intimation"], []),
    ("credit_rating", [r"credit rating", r"\brating\b"], []),
    ("pledging", [r"pledge", r"encumbrance", r"invocation"], []),
    ("insider_trading", [r"insider trading", r"\bsast\b", r"takeover regulations", r"regulation 7\s*\(2\)", r"regulation 29",
                         r"acquisition of shares by promoter", r"disclosure of change in shareholding"], []),
    ("management_change", [r"change in (directors?|management|key managerial|kmp|auditor)", r"appointment",
                           r"resignation", r"cessation", r"re-?appointment", r"chief (executive|financial)",
                           r"managing director"], []),
    ("M&A", [r"acquisition", r"amalgamation", r"merger", r"scheme of arrangement", r"demerger",
             r"divest", r"disinvest", r"sale of (stake|business|undertaking)"], []),
    ("litigation", [r"litigation", r"dispute", r"\border\b", r"penalt", r"show cause", r"\bnclt\b",
                    r"insolvency", r"demand notice", r"regulatory action", r"fraud", r"default"], []),
    ("fund_raise", [r"\bqip\b", r"preferential", r"rights issue", r"allotment", r"debenture", r"\bncds?\b",
                    r"commercial paper", r"fund ?rais", r"issue of securities", r"bonds?\b", r"warrants"], []),
    ("dividend", [r"dividend"], []),
    ("bonus_split", [r"\bbonus\b", r"\bsplit\b", r"sub-?division"], []),
    ("capex", [r"capacity", r"capex", r"commission", r"new plant", r"commercial production", r"expansion"], []),
    ("press_release", [r"press release", r"media release", r"\border(s)? (win|received|bagged)", r"bagging",
                       r"receiving of orders?", r"award of order", r"letter of award", r"contract"], []),
    ("agm_egm", [r"\bagm\b", r"\begm\b", r"general meeting", r"annual report"], []),
    ("postal_ballot", [r"postal ballot", r"e-?voting"], []),
]
_COMPILED = [(c, [re.compile(p, re.I) for p in sp], [re.compile(p, re.I) for p in tp]) for c, sp, tp in _RULES]


def classify_rules(subject: str, text: str = "") -> str:
    for cat, subj_pats, text_pats in _COMPILED:
        if any(p.search(subject) for p in subj_pats):
            if text_pats and not any(p.search(text) or p.search(subject) for p in text_pats):
                continue
            return cat
    # Weak signal from the free-text body when the subject is generic ("General Updates")
    for cat, subj_pats, _ in _COMPILED:
        if cat in ("routine", "investor_meetings", "earnings_call"):
            continue
        if any(p.search(text[:600]) for p in subj_pats):
            return cat
    return "unclassified"


# ---- subtype detection: what moves a category's default tier up or down ----
_TOP_ROLE = re.compile(r"\b(ceo|cfo|chief executive|chief financial|managing director|\bmd\b|whole[- ]time director|chairman|chairperson)\b", re.I)
_INDEP = re.compile(r"independent director|non-executive", re.I)
_DOWNGRADE = re.compile(r"downgrad|revised (?:its |the )?rating .*from .* to|placed on (?:credit )?watch with negative|outlook.*negative", re.I)
_UPGRADE = re.compile(r"upgrad", re.I)
_REAFFIRM = re.compile(r"reaffirm|re-affirm", re.I)
_REGULATOR = re.compile(r"\b(sebi|rbi|cci|nclt|insolvency|enforcement directorate|cbi|income tax|gst|usfda|warning letter|import alert)\b", re.I)
_PROMOTER = re.compile(r"promoter", re.I)


def subtype(category: str, subject: str, text: str) -> str:
    blob = f"{subject} {text}"
    if category == "management_change":
        if _TOP_ROLE.search(blob):
            return "top"
        if _INDEP.search(blob):
            return "independent"
        return "other"
    if category == "credit_rating":
        if _DOWNGRADE.search(blob) and not _UPGRADE.search(blob):
            return "downgrade"
        if _UPGRADE.search(blob):
            return "upgrade"
        if _REAFFIRM.search(blob):
            return "reaffirm"
        return "other"
    if category == "litigation":
        return "regulator" if _REGULATOR.search(blob) else "other"
    if category == "insider_trading":
        return "promoter" if _PROMOTER.search(blob) else "other"
    if category == "press_release":
        return "order_win" if re.search(r"\border|contract|letter of award|loa\b", blob, re.I) else "other"
    return ""


def classify(subject: str, text: str = "", use_model: bool = True) -> tuple[str, str]:
    cat = classify_rules(subject, text)
    if cat == "unclassified" and use_model:
        from . import llm

        if llm.available("classify"):
            try:
                out = llm.call(
                    "classify",
                    "Classify this Indian stock-exchange filing into exactly one category from this list: "
                    f"{', '.join(CATEGORIES)}.\nSubject: {subject}\nText: {text[:800]}\n"
                    'Reply as JSON: {"category": "..."}',
                )
                if out.get("category") in CATEGORIES:
                    cat = out["category"]
            except Exception:
                pass
    return cat, subtype(cat, subject, text)
