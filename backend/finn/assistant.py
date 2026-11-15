"""FINN button: ask / command / go. Rules route most requests for free; the small model handles the
rest; the mid/strong model is called only for an Ask that needs reasoning over documents."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm, rules
from .feed import card
from .models import Filing, Research

_GO = re.compile(r"^\s*(open|go to|show( me)?|take me to|pull up)\b", re.I)
_CMD = re.compile(r"\b(alert|remind|notify|tell me (if|when)|let me know|watch|ping me|warn me)\b", re.I)

ANSWER_PROMPT = """You are FINN, an investment research assistant. Answer the investor's question using ONLY the sources below.
Never predict prices or give advice. If the sources don't answer it, say exactly "Not in the sources." and nothing else.
Keep it to at most 3 short sentences. Cite every claim with the source id in brackets, e.g. [F1] or [card:promise].
Context: the investor is looking at {context}.
Question: {q}
Sources:
{sources}
Return JSON: {{"answer": "", "cites": ["F1"]}}"""


def route(s: Session, text: str, ctx: dict) -> dict:
    """ctx = {"screen": "feed|company|filing|watch", "ticker": "...", "filing_id": "..."}"""
    text = (text or "").strip()
    if not text:
        return {"intent": "none", "say": "I didn't catch that."}
    if _GO.search(text) and not _CMD.search(text):
        tickers = rules.resolve_tickers(s, text)
        if tickers:
            return {"intent": "go", "route": f"/company/{tickers[0]}", "say": f"Opening {tickers[0]}."}
        if re.search(r"watch|rules|alerts", text, re.I):
            return {"intent": "go", "route": "/watch", "say": "Opening your watch list."}
        if re.search(r"portfolio|holdings", text, re.I):
            return {"intent": "go", "route": "/portfolio", "say": "Opening your portfolio."}
    if _CMD.search(text):
        # "this company" / "it" -> screen context
        t2 = text
        if ctx.get("ticker") and not rules.resolve_tickers(s, text):
            t2 = f"{text} {ctx['ticker']}"
        res = rules.parse_rule(s, t2)
        if "spec" in res:
            return {"intent": "command", "rule": res, "say": f"Watch {res['label']}?"}
        say = res["error"] + (f" Closest I can watch: {rules.label(res['closest'])}." if res.get("closest") else "")
        return {"intent": "command", "error": res["error"], "closest": res.get("closest"),
                "closest_label": rules.label(res["closest"]) if res.get("closest") else None, "say": say}
    return ask(s, text, ctx)


def ask(s: Session, q: str, ctx: dict) -> dict:
    tickers = rules.resolve_tickers(s, q) or ([ctx["ticker"]] if ctx.get("ticker") else [])
    sources, ids = [], {}
    since = datetime.utcnow() - timedelta(days=10)
    fq = select(Filing).where(Filing.filed_at >= since, Filing.tier.in_(["S", "A", "B"]))
    if tickers:
        fq = fq.where(Filing.ticker.in_(tickers))
    if ctx.get("filing_id"):
        f0 = s.get(Filing, ctx["filing_id"])
        if f0:
            tickers = tickers or [f0.ticker]
    filings = s.scalars(fq.order_by(Filing.score.desc()).limit(8)).all()
    for i, f in enumerate(filings, 1):
        sid = f"F{i}"
        ids[sid] = {"type": "filing", "id": f.id, "label": f.headline}
        pm = f.price_move or {}
        sources.append(f"[{sid}] {f.filed_at:%d %b} {f.ticker} {f.category}: {f.headline}. {f.summary}"
                       + (f" Stock {pm['pct']:+.1f}% that day on {pm.get('vol_ratio') or 0:.1f}× volume." if pm.get("pct") is not None else ""))
    for t in tickers[:2]:
        r = s.get(Research, t)
        if r:
            for cid, c in (r.view.get("cards") or {}).items():
                sid = f"card:{cid}" if len(tickers) == 1 else f"card:{t}:{cid}"
                ids[sid] = {"type": "card", "ticker": t, "card": cid}
                sources.append(f"[{sid}] {str(c)[:3500]}")
    if not sources:
        return {"intent": "ask", "answer": "Not in the sources.", "cites": [], "say": "I don't have anything on that yet."}
    if not llm.available("answer"):
        top = filings[0] if filings else None
        if top:
            return {"intent": "ask", "answer": f"{top.headline}. {top.summary}", "cites": [ids["F1"]], "items": [card(f) for f in filings[:3]],
                    "say": top.headline}
        return {"intent": "ask", "answer": "Not in the sources.", "cites": [], "say": "I don't have anything on that yet."}
    context = f"the {ctx.get('screen', 'feed')} screen" + (f" for {ctx['ticker']}" if ctx.get("ticker") else "")
    out = llm.call("answer", ANSWER_PROMPT.format(context=context, q=q, sources="\n".join(sources)[:60_000]))
    answer = out.get("answer", "Not in the sources.")
    cites = [ids[c] for c in out.get("cites", []) if c in ids]
    first = re.split(r"(?<=[.!?])\s", re.sub(r"\[[^\]]+\]", "", answer).strip())
    return {"intent": "ask", "answer": answer, "cites": cites, "say": " ".join(first[:2])}
