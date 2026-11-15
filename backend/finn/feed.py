"""Windowed digest: S, A, B sections plus one counted C row."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Filing
from .score import CATEGORY_LABEL

WINDOWS = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}


def card(f: Filing, full: bool = False) -> dict:
    d = {
        "id": f.id, "ticker": f.ticker, "company": f.company, "tier": f.tier, "score": f.score,
        "category": f.category, "category_label": CATEGORY_LABEL.get(f.category, f.category),
        "headline": f.headline, "summary": f.summary, "filed_at": f.filed_at.isoformat(),
        "why": (f.factors or {}).get("why", []), "sector": (f.factors or {}).get("sector", ""),
        "card": f.card or {}, "price_move": f.price_move or {}, "source_url": f.attachment_url,
        "pinned": f.pinned,
    }
    if full:
        d.update({"subject": f.subject, "text": f.text, "factors": f.factors})
    return d


def feed(s: Session, window: str = "24h", hours: int | None = None, now: datetime | None = None) -> dict:
    h = hours or WINDOWS.get(window, 24)
    now = now or datetime.utcnow()
    since = now - timedelta(hours=h)
    rows = s.scalars(select(Filing).where(Filing.filed_at >= since, Filing.dismissed.is_(False))
                     .order_by(Filing.score.desc(), Filing.filed_at.desc())).all()
    out = {"window_hours": h, "since": since.isoformat(), "S": [], "A": [], "B": [], "C": {"count": 0, "by_category": {}, "items": []}}
    for f in rows:
        if f.tier == "C":
            out["C"]["count"] += 1
            lbl = CATEGORY_LABEL.get(f.category, f.category)
            out["C"]["by_category"][lbl] = out["C"]["by_category"].get(lbl, 0) + 1
            out["C"]["items"].append({"id": f.id, "ticker": f.ticker, "headline": f.headline, "category_label": lbl})
        else:
            out[f.tier].append(card(f))
    pinned = [c for t in "SAB" for c in out[t] if c["pinned"]]
    out["pinned"] = pinned
    out["counts"] = {t: len(out[t]) for t in "SAB"} | {"C": out["C"]["count"]}
    return out
