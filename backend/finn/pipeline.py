"""Batch path: filings -> classify -> enrich (S/A only) -> score -> merge same-day price moves."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, enrich, llm
from .classify import classify
from .models import Event, Filing, Holding, Price, Setting
from .score import Portfolio, score_filing

log = logging.getLogger("finn.pipeline")


def load_portfolio_file(s: Session) -> None:
    """Seed holdings from data/portfolio.json (idempotent)."""
    data = json.loads(config.PORTFOLIO_PATH.read_text())
    for h in data["holdings"]:
        row = s.get(Holding, h["ticker"]) or Holding(ticker=h["ticker"])
        row.name, row.sector, row.weight = h.get("name", ""), h.get("sector", ""), float(h.get("weight", 0))
        s.merge(row)
    if not s.get(Setting, "prefs"):
        s.add(Setting(key="prefs", value={"starred_categories": data.get("starred_categories", []),
                                         "price_pct": config.DEFAULT_PRICE_PCT, "vol_ratio": config.DEFAULT_VOL_RATIO}))
    # sector map for non-holdings (sector peers): ticker -> sector
    if data.get("aliases"):
        s.merge(Setting(key="aliases", value=data["aliases"]))
    if data.get("peers"):
        s.merge(Setting(key="peer_sectors", value=data["peers"]))


def portfolio(s: Session) -> Portfolio:
    hs = s.scalars(select(Holding)).all()
    prefs = (s.get(Setting, "prefs") or Setting(value={})).value
    return Portfolio(
        holdings={h.ticker: {"sector": h.sector, "weight": h.weight, "starred": h.starred, "name": h.name} for h in hs},
        starred_categories=set(prefs.get("starred_categories", [])),
    )


def sector_of(s: Session, ticker: str, industry: str = "") -> str:
    h = s.get(Holding, ticker)
    if h:
        return h.sector
    peers = (s.get(Setting, "peer_sectors") or Setting(value={})).value
    return peers.get(ticker, "")


def day_move(s: Session, symbol: str, day: date) -> dict:
    """% change vs previous close and volume ÷ 20-day average, for `day`."""
    rows = s.scalars(select(Price).where(Price.symbol == symbol, Price.day <= day).order_by(Price.day.desc()).limit(21)).all()
    if len(rows) < 2 or rows[0].day != day:
        return {}
    pct = (rows[0].close - rows[1].close) / rows[1].close * 100
    prior = [r.volume for r in rows[1:] if r.volume]
    vr = rows[0].volume / (sum(prior) / len(prior)) if prior and rows[0].volume else None
    return {"day": day.isoformat(), "pct": round(pct, 2), "vol_ratio": round(vr, 2) if vr else None, "close": rows[0].close}


class MoveCache:
    """Loads prices for many symbols in one query; computes day moves in memory."""

    def __init__(self, s: Session, symbols: set[str], since: date):
        self.by_sym: dict[str, list[Price]] = {}
        syms = list(symbols)
        for i in range(0, len(syms), 500):
            for p in s.scalars(select(Price).where(Price.symbol.in_(syms[i : i + 500]), Price.day >= since - timedelta(days=40))).all():
                self.by_sym.setdefault(p.symbol, []).append(p)
        for v in self.by_sym.values():
            v.sort(key=lambda p: p.day, reverse=True)

    def move(self, symbol: str, day: date) -> dict:
        rows = [p for p in self.by_sym.get(symbol, []) if p.day <= day][:21]
        if len(rows) < 2 or rows[0].day != day:
            return {}
        pct = (rows[0].close - rows[1].close) / rows[1].close * 100
        prior = [r.volume for r in rows[1:] if r.volume]
        vr = rows[0].volume / (sum(prior) / len(prior)) if prior and rows[0].volume else None
        return {"day": day.isoformat(), "pct": round(pct, 2), "vol_ratio": round(vr, 2) if vr else None, "close": rows[0].close}


def upsert_filings(s: Session, rows: list[dict]) -> list[str]:
    """Insert new filings, classify them. Returns ids of new rows."""
    new_ids = []
    ids = [r["id"] for r in rows if r.get("ticker")]
    existing: set[str] = set()
    for i in range(0, len(ids), 500):  # one round trip per 500 ids, not one per filing
        existing |= set(s.scalars(select(Filing.id).where(Filing.id.in_(ids[i : i + 500]))).all())
    seen: set[str] = set()
    for r in rows:
        if not r.get("ticker") or r["id"] in existing or r["id"] in seen:
            continue
        seen.add(r["id"])
        cat, sub = classify(r["subject"], r.get("text", ""), use_model=False)
        f = Filing(id=r["id"][:80], ticker=r["ticker"][:32], company=(r.get("company") or "")[:200], subject=(r["subject"] or "")[:300],
                   text=r.get("text", ""), attachment_url=(r.get("attachment_url") or "")[:500],
                   filed_at=datetime.fromisoformat(r["filed_at"]), category=cat, subtype=sub)
        f.headline, f.summary = enrich.fallback_headline(f.company, f.subject, f.text)
        s.add(f)
        new_ids.append(f.id)
        if cat == "board_meeting":
            d = enrich.board_meeting_date(f.text)
            if d and not s.scalars(select(Event).where(Event.ticker == f.ticker, Event.event == "results_board_meeting", Event.day == d)).first():
                s.add(Event(ticker=f.ticker, event="results_board_meeting", day=d, source_filing=f.id))
    s.flush()
    return new_ids


_SECTORS: dict[int, dict[str, str]] = {}


def _sector_map(s: Session, pf: Portfolio) -> dict[str, str]:
    key = id(pf)
    if key not in _SECTORS:
        peers = (s.get(Setting, "peer_sectors") or Setting(value={})).value
        _SECTORS.clear()
        _SECTORS[key] = {**peers, **{t: h["sector"] for t, h in pf.holdings.items()}}
    return _SECTORS[key]


def rescore(s: Session, f: Filing, pf: Portfolio) -> None:
    sector = _sector_map(s, pf).get(f.ticker, "")
    f.score, f.tier, f.factors = score_filing(f.ticker, sector, f.category, f.subtype, f.card or {}, f.price_move or {}, pf)
    f.factors = {**f.factors, "sector": sector}


def process(s: Session, ids: list[str] | None = None, download=None, screener=None, use_models: bool = True) -> dict:
    """Score everything (or `ids`), then enrich what lands in S/A and rescore.
    `download(url)->bytes` fetches PDFs (NSE client from the laptop). `screener(ticker)` returns parsed
    quarterly table for the no-model results fallback / cross-check."""
    pf = portfolio(s)
    q = select(Filing)
    if ids is not None:
        q = q.where(Filing.id.in_(ids))
    filings = s.scalars(q).all()
    stats = {"scored": 0, "enriched": 0, "S": 0, "A": 0, "B": 0, "C": 0}

    # cheap pass: ambiguous filings for holdings/peers go to the small model
    sectors = _sector_map(s, pf)
    if use_models and llm.available("classify"):
        for f in filings:
            if f.category == "unclassified" and f.ticker in pf.holdings:
                f.category, f.subtype = classify(f.subject, f.text, use_model=True)

    if filings:
        mc = MoveCache(s, {f.ticker for f in filings}, min(f.filed_at for f in filings).date())
        for f in filings:
            f.price_move = mc.move(f.ticker, f.filed_at.date()) or f.price_move or {}
            rescore(s, f, pf)

    last_results: dict[str, datetime] = {}
    for f in sorted(filings, key=lambda x: x.filed_at):
        if f.category != "results":
            continue
        prev = last_results.get(f.ticker)
        if prev and (f.filed_at - prev) < timedelta(days=5):
            f.subtype = "dup"
            rescore(s, f, pf)
        else:
            last_results[f.ticker] = f.filed_at

    to_summarise = []
    for f in filings:
        if f.tier not in ("S", "A") or f.enriched:
            continue
        try:
            enrich_one(s, f, download, screener, use_models)
        except Exception as e:
            log.warning("enrich %s failed: %s", f.id, e)
        if f.category not in ("results", "management_change") and use_models:
            to_summarise.append({"id": f.id, "company": f.company, "subject": f.subject, "text": f.text})
        f.enriched = True
        stats["enriched"] += 1
        rescore(s, f, pf)

    if to_summarise and llm.available("summary"):
        for fid, it in enrich.summarise(to_summarise).items():
            f = s.get(Filing, fid)
            if f:
                f.headline = it.get("headline") or f.headline
                f.summary = it.get("summary") or f.summary
                f.card = {**(f.card or {}), **(it.get("fields") or {})}
                rescore(s, f, pf)

    for f in filings:
        f.headline = (f.headline or "")[:200]  # Postgres enforces column lengths; SQLite doesn't
        stats["scored"] += 1
        stats[f.tier] += 1
    return stats


def enrich_one(s: Session, f: Filing, download, screener, use_models: bool) -> None:
    short = enrich.fallback_headline(f.company, "", "")[0].rstrip(": ")
    if f.category == "results":
        sq = screener(f.ticker) if screener else None
        card = {}
        if use_models and download and f.attachment_url and llm.available("results"):
            try:
                cur_q = None
                if sq:
                    sc = enrich.results_from_screener(sq)
                    cur_q = {"revenue": (sc.get("revenue") or {}).get("q")}
                card = enrich.extract_results(download(f.attachment_url), cur_q)
                card["source"] = "results filing"
            except Exception as e:
                log.warning("results PDF extraction failed for %s: %s", f.ticker, e)
        if not card and sq:
            card = enrich.results_from_screener(sq)
        if card:
            f.card = card
            pat = card.get("pat") or {}
            if pat.get("yoy_pct") is not None:
                f.headline = f"{short}: PAT {pat['yoy_pct']:+.0f}% YoY in {card.get('period', 'the quarter')}"
    elif f.category == "management_change" and use_models and llm.available("bio"):
        pdf = None
        if download and f.attachment_url:
            try:
                pdf = download(f.attachment_url)
            except Exception:
                pdf = None
        bio = enrich.extract_bio(f.text, pdf)
        f.card = {**(f.card or {}), **bio}
        left = ", ".join(f"{x.get('role')} {x.get('name')}" for x in bio.get("left") or [] if x.get("name"))
        joined = ", ".join(f"{x.get('name')} as {x.get('role')}" for x in bio.get("joined") or [] if x.get("name"))
        if joined or left:
            f.headline = f"{short}: " + (f"{joined} joins" if joined else "") + ("; " if joined and left else "") + (f"{left} leaves" if left else "")


def merge_price_alerts(s: Session, day: date) -> list[Filing]:
    """EOD: attach the day's move to same-day filings for that company and rescore."""
    pf = portfolio(s)
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1, hours=6)  # include after-market filings timestamped late
    out = []
    for f in s.scalars(select(Filing).where(Filing.filed_at >= start, Filing.filed_at < end)).all():
        mv = day_move(s, f.ticker, day)
        if mv and (abs(mv["pct"]) >= config.DEFAULT_PRICE_PCT or (mv.get("vol_ratio") or 0) >= config.DEFAULT_VOL_RATIO):
            f.price_move = mv
            old = f.tier
            rescore(s, f, pf)
            out.append(f)
            log.info("merged move %s %s%% (tier %s->%s)", f.ticker, mv["pct"], old, f.tier)
    return out
