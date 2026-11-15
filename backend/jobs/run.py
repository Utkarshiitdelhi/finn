"""Batch jobs. Run from the backend folder:

  python -m jobs.run poll            # fetch filings (NSE→BSE), classify, score, enrich S/A, filing rules, push S
  python -m jobs.run eod             # prices + macro, merge moves into same-day filings, price/volume/macro/event rules, push
  python -m jobs.run brief           # morning (8:30) / evening (4:30) A-tier brief notification
  python -m jobs.run research INFY TCS   # build/refresh Company views (promise tracker etc.)
  python -m jobs.run load-snapshot   # load committed snapshots into the DB (no network needed)
  python -m jobs.run all             # poll + eod + research for the demo set

NSE blocks most cloud IPs: run `poll` from your laptop with DATABASE_URL pointing at Supabase.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import select

from finn import config, ingest, pipeline, push, rules
from finn.db import init_db, session_scope
from finn.models import Filing, Holding, Price
from finn.research import screener
from finn.research import view as research

log = logging.getLogger("finn.jobs")
DEMO_RESEARCH = ["INFY", "HDFCBANK"]


def _tickers() -> list[str]:
    with session_scope() as s:
        return [h.ticker for h in s.scalars(select(Holding)).all()]


def _screener_quarters(ticker: str):
    try:
        return screener.company(ticker)["quarters"]
    except Exception as e:
        log.warning("screener %s: %s", ticker, e)
        return None


def _relevant(rows: list[dict]) -> list[dict]:
    """Keep holdings and sector peers; the rest of the market can't reach S/A/B for this investor."""
    import json

    data = json.loads(config.PORTFOLIO_PATH.read_text())
    keep = {h["ticker"] for h in data["holdings"]} | set(data.get("peers", {}))
    return [r for r in rows if r.get("ticker") in keep]


def _store_filings(rows: list[dict]) -> list[str]:
    with session_scope() as s:
        return pipeline.upsert_filings(s, rows)


def poll(days: int = 7) -> None:
    init_db()
    with session_scope() as s:
        if not s.scalars(select(Holding)).first():
            pipeline.load_portfolio_file(s)
        rules.ensure_defaults(s)
    rows = ingest.fetch_filings(_tickers(), days=days)
    ingest.save_snapshot(f"filings-{date.today():%Y%m%d}.json", rows)
    ingest.save_snapshot("filings-latest.json", rows)
    rows = _relevant(rows)
    new_ids = _store_filings(rows)
    log.info("%d relevant filings (holdings + sector peers), %d new", len(rows), len(new_ids))
    nse = ingest.NSE()
    with session_scope() as s:
        stats = pipeline.process(s, new_ids, download=nse.download, screener=_screener_quarters)
        log.info("scored: %s", stats)
        new = s.scalars(select(Filing).where(Filing.id.in_(new_ids))).all()
        hits = rules.evaluate_filings(s, new)
        n = push.push_new_s_tier(s) + push.push_rule_hits(s, hits)
        log.info("%d rule hits, %d pushes", len(hits), n)


def _store_prices(rows: list[dict]) -> None:
    with session_scope() as s:
        for r in rows:
            d = date.fromisoformat(r["day"])
            p = s.scalars(select(Price).where(Price.symbol == r["symbol"], Price.day == d)).first()
            if p:
                p.close, p.volume = r["close"], r["volume"]
            else:
                s.add(Price(symbol=r["symbol"], day=d, close=r["close"], volume=r["volume"]))


def eod(day: date | None = None) -> None:
    init_db()
    rows = ingest.fetch_prices(_tickers() + list(ingest.MACRO), days=45)
    ingest.save_snapshot("prices-latest.json", rows)
    _store_prices(rows)
    with session_scope() as s:
        day = day or max((date.fromisoformat(r["day"]) for r in rows if r["symbol"] not in ingest.MACRO), default=date.today())
        merged = pipeline.merge_price_alerts(s, day)
        hits = rules.evaluate_eod(s, day)
        n = push.push_new_s_tier(s) + push.push_rule_hits(s, hits)
        log.info("EOD %s: %d merged, %d hits, %d pushes", day, len(merged), len(hits), n)


def brief() -> None:
    init_db()
    hour = (datetime.utcnow() + timedelta(hours=5, minutes=30)).hour
    since = datetime.utcnow() - timedelta(hours=16 if hour < 12 else 8)
    with session_scope() as s:
        log.info("brief pushes: %d", push.push_brief(s, since))


def build_research(tickers: list[str] | None = None) -> None:
    init_db()
    for t in tickers or DEMO_RESEARCH:
        try:
            v = research.build(t)
            log.info("%s: %s", t, v["cards"]["promise"]["scorecard"]["text"])
        except Exception as e:
            log.warning("research %s failed: %s", t, e)


def load_snapshot() -> None:
    init_db()
    with session_scope() as s:
        if not s.scalars(select(Holding)).first():
            pipeline.load_portfolio_file(s)
        rules.ensure_defaults(s)
    prices = ingest.load_snapshot("prices-latest.json") or []
    _store_prices(prices)
    rows = _relevant(ingest.load_snapshot("filings-latest.json") or [])
    new_ids = _store_filings(rows)
    with session_scope() as s:
        log.info("snapshot: %d prices, %d new filings, %s", len(prices), len(new_ids),
                 pipeline.process(s, new_ids, screener=_screener_quarters))


def all_() -> None:
    poll()
    eod()
    build_research()


JOBS = {"poll": poll, "eod": eod, "brief": brief, "research": build_research, "load-snapshot": load_snapshot, "all": all_}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if len(sys.argv) < 2 or sys.argv[1] not in JOBS:
        print(__doc__)
        sys.exit(1)
    name, args = sys.argv[1], sys.argv[2:]
    if name == "research":
        build_research([a.upper() for a in args] or None)
    elif name == "poll" and args:
        poll(int(args[0]))
    else:
        JOBS[name]()
