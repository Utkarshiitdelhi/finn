"""Expo push service. S-tier filings and rule hits go straight to the phone; A-tier waits for the
8:30 am / 4:30 pm brief."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Filing, PushToken, RuleHit

log = logging.getLogger("finn.push")
EXPO_URL = "https://exp.host/--/api/v2/push/send"


def send(s: Session, messages: list[dict]) -> int:
    tokens = [t.token for t in s.scalars(select(PushToken)).all()]
    if not tokens or not messages:
        return 0
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if config.EXPO_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {config.EXPO_ACCESS_TOKEN}"
    batch = [{**m, "to": t, "sound": "default", "channelId": "default"} for m in messages for t in tokens]
    sent = 0
    for i in range(0, len(batch), 100):
        r = httpx.post(EXPO_URL, json=batch[i : i + 100], headers=headers, timeout=30)
        if r.status_code != 200:
            log.warning("expo push %s: %s", r.status_code, r.text[:300])
            continue
        for tok, res in zip(batch[i : i + 100], r.json().get("data", [])):
            if res.get("status") == "error" and (res.get("details") or {}).get("error") == "DeviceNotRegistered":
                s.query(PushToken).filter(PushToken.token == tok["to"]).delete()
            else:
                sent += 1
    return sent


def push_new_s_tier(s: Session) -> int:
    recent = datetime.utcnow() - timedelta(days=2)
    fs = s.scalars(select(Filing).where(Filing.tier == "S", Filing.pushed.is_(False), Filing.filed_at >= recent)).all()
    msgs = [{"title": f.headline[:80], "body": f.summary[:160] or f.subject,
             "data": {"url": f"/filing/{f.id}"}} for f in fs]
    n = send(s, msgs)
    for f in fs:
        f.pushed = True
    return n


def push_rule_hits(s: Session, hits: list[RuleHit]) -> int:
    msgs = []
    for h in hits:
        p = h.payload or {}
        url = f"/filing/{p['filing_id']}" if p.get("filing_id") else (f"/company/{p['ticker']}" if p.get("ticker") else "/watch")
        if p.get("impact"):
            url = f"/impact/{p['series']}"
        msgs.append({"title": "FINN alert", "body": h.message[:180], "data": {"url": url}})
        h.pushed = True
    return send(s, msgs)


def push_brief(s: Session, since: datetime) -> int:
    """Morning / evening brief: one notification for all new A items (+ S items already pushed)."""
    fs = s.scalars(select(Filing).where(Filing.filed_at >= since, Filing.tier.in_(["S", "A"]))).all()
    hidden = s.query(Filing).filter(Filing.filed_at >= since, Filing.tier.in_(["B", "C"])).count()
    if not fs:
        return 0
    names = ", ".join(f.headline.split(":")[0] + " " + f.category.replace("_", " ") for f in fs[:3])
    body = f"{len(fs)} thing{'s' if len(fs) != 1 else ''} need you: {names}. {hidden} routine filings hidden."
    return send(s, [{"title": "Your FINN brief", "body": body, "data": {"url": "/"}}])
