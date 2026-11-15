"""Company research view: ticker -> screener page -> documents -> extract -> cache.
Each card carries its sources; the strong model only sees the cards, never the web."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from .. import llm
from ..db import session_scope
from ..models import Document, Exposure, GuidanceClaim, Job, Research
from . import promise, screener

log = logging.getLogger("finn.research")
EXPOSURE_FACTORS = ["crude oil", "USD/INR", "interest rates", "steel", "coal and power", "monsoon and rural demand",
                    "US tech spending", "government capex", "gold"]
FACTOR_SERIES = {"CL=F": "crude oil", "USDINR=X": "USD/INR", "GC=F": "gold", "^NSEI": None}


def _step(job_id: str, msg: str) -> None:
    with session_scope() as s:
        j = s.get(Job, job_id) or Job(id=job_id, steps=[])
        j.steps = [*(j.steps or []), {"at": datetime.utcnow().isoformat(), "msg": msg}]
        j.status = "running"
        s.merge(j)
    log.info("[%s] %s", job_id, msg)


def _cagr(series: list, years: int):
    vals = [v for v in series if v is not None]
    if len(vals) <= years or vals[-1 - years] in (None, 0) or vals[-1] is None or vals[-1 - years] <= 0 or vals[-1] <= 0:
        return None
    return round(((vals[-1] / vals[-1 - years]) ** (1 / years) - 1) * 100, 1)


def numbers_card(sc: dict) -> dict:
    pl, q = sc["profit_loss"], sc["quarters"]
    periods = [p for p in pl["periods"] if p.upper() != "TTM"]
    n = len(periods)
    g = lambda tbl, *names: next((tbl["rows"][x] for x in names if x in tbl["rows"]), [])  # noqa: E731
    sales, opp, np_ = g(pl, "Sales", "Revenue")[:n], g(pl, "Operating Profit", "Financing Profit")[:n], g(pl, "Net Profit")[:n]
    opm = g(pl, "OPM %", "Financing Margin %")[:n]
    years = periods[-5:]
    table = [{"period": p, "revenue": sales[i], "operating_profit": opp[i] if i < len(opp) else None,
              "opm_pct": opm[i] if i < len(opm) else None, "pat": np_[i] if i < len(np_) else None}
             for i, p in enumerate(periods) if p in years]
    qs = q["periods"][-8:]
    qrev = g(q, "Sales", "Revenue")[-8:]
    qpat = g(q, "Net Profit")[-8:]
    return {"id": "numbers", "title": "Numbers + trajectory", "unit": "₹ crore", "years": table,
            "cagr": {"revenue_3y": _cagr(sales, 3), "revenue_5y": _cagr(sales, 5), "pat_3y": _cagr(np_, 3), "pat_5y": _cagr(np_, 5)},
            "quarters": [{"period": p, "revenue": qrev[i] if i < len(qrev) else None, "pat": qpat[i] if i < len(qpat) else None} for i, p in enumerate(qs)],
            "source": "Exchange-reported results, standardised by screener.in"}


def cash_card(sc: dict) -> dict:
    cf, pl = sc["cash_flow"], sc["profit_loss"]
    cfo_row = next((v for k, v in cf["rows"].items() if k.lower().startswith("cash from operating")), [])
    pl_periods = [p for p in pl["periods"] if p.upper() != "TTM"]
    pat_by = dict(zip(pl_periods, pl["rows"].get("Net Profit", [])))
    years = []
    for p, cfo in list(zip(cf["periods"], cfo_row))[-5:]:
        pat = pat_by.get(p)
        years.append({"period": p, "cfo": cfo, "pat": pat, "ratio": round(cfo / pat, 2) if cfo is not None and pat else None})
    tc, tp = sum(y["cfo"] or 0 for y in years), sum(y["pat"] or 0 for y in years)
    ratio = round(tc / tp, 2) if tp > 0 else None
    verdict = None if ratio is None else ("Profits are backed by cash" if ratio >= 0.9 else "Cash lags reported profit" if ratio >= 0.7 else "Cash well below reported profit")
    return {"id": "cash", "title": "Cash quality", "years": years, "cfo_to_pat_5y": ratio, "line": verdict,
            "note": "Cash from operations ÷ net profit; FCF needs the capex schedule (not computed).",
            "source": "Cash-flow statements, standardised by screener.in"}


def balance_card(sc: dict) -> dict:
    bs = sc["balance_sheet"]
    r = bs["rows"]
    eq, res, debt = r.get("Equity Capital", []), r.get("Reserves", []), r.get("Borrowings", [])
    out = []
    for i, p in enumerate(bs["periods"][-5:]):
        j = len(bs["periods"]) - 5 + i if len(bs["periods"]) >= 5 else i
        e = (eq[j] or 0) + (res[j] or 0) if j < len(eq) and j < len(res) else None
        d = debt[j] if j < len(debt) else None
        out.append({"period": p, "debt": d, "equity": e, "de": round(d / e, 2) if d is not None and e else None})
    return {"id": "balance", "title": "Balance sheet", "years": out, "source": "Balance sheets, standardised by screener.in"}


def _ar_sections(pages: list[str]) -> list[tuple[int, str]]:
    """Cut an annual report to business overview, segment note, MD&A and risk pages by heading search."""
    pat = re.compile(r"management discussion|business overview|segment (information|reporting|results)|risks? and (concerns|mitigation)|risk management|our businesses|operating segments", re.I)
    picked = [(i + 1, p) for i, p in enumerate(pages) if pat.search(p[:400])]
    if len(picked) < 3:
        picked = [(i + 1, p) for i, p in enumerate(pages) if pat.search(p)]
    return picked[:25]


SNAPSHOT_PROMPT = """From these annual-report pages of {name}, write a business snapshot. Use ONLY these pages.
Return JSON: {{"what_it_does": "≤ 2 sentences", "segments": [{{"name": "", "share_of_revenue_pct": null, "page": 0}}],
 "key_facts": [{{"fact": "≤ 15 words, numbers preferred", "page": 0, "quote": "exact supporting phrase"}}]}} (max 4 key facts)
{text}"""

EXPOSURE_PROMPT = """From these annual-report pages of {name}, list the company's OWN disclosed exposures to these outside factors:
{factors}. Only include a factor if the report itself says it matters (raw material, input cost, revenue driver, currency,
borrowing cost...). Use ONLY these pages.
Return JSON: {{"exposures": [{{"factor": "one of the list", "direction": "helps|hurts" (effect of the factor RISING),
 "strength": "high|medium|low", "quote": "exact sentence from the page", "page": 0}}]}}
{text}"""

BULLBEAR_PROMPT = """You are given research cards about {name}. Write the 3 strongest bull points and 3 strongest bear points
an investor could draw from THESE CARDS ONLY. No outside knowledge, no predictions, no advice. Each point ≤ 20 words and
must cite the card id(s) it rests on (ids: {ids}).
Return JSON: {{"bull": [{{"point": "", "cites": ["numbers"]}}], "bear": [{{"point": "", "cites": ["promise"]}}]}}
Cards: {cards}"""


def build(ticker: str, max_calls: int = 6, use_models: bool = True) -> dict:
    ticker = ticker.upper()
    job_id = f"research:{ticker}"
    with session_scope() as s:
        s.merge(Job(id=job_id, status="running", steps=[], error=""))
    try:
        _step(job_id, "Reading screener.in page…")
        sc = screener.company(ticker)
        name = sc["name"] or ticker
        cards: dict = {"numbers": numbers_card(sc), "cash": cash_card(sc), "balance": balance_card(sc)}
        cards["snapshot"] = {"id": "snapshot", "title": "Snapshot", "what_it_does": sc["about"], "segments": [], "key_facts": [],
                             "source": "Company profile on screener.in (annual report not read yet)"}

        # --- promise tracker ---
        transcripts = sc["docs"]["transcripts"][:max_calls]
        all_claims: list[dict] = []
        if transcripts and use_models and llm.available("claims"):
            for t in reversed(transcripts):  # oldest first
                _step(job_id, f"Reading {t['period']} transcript…")
                try:
                    pdf = screener.download_pdf(t["url"])
                    pages = screener.pdf_pages(pdf)
                    if sum(len(p) for p in pages) < 2000:
                        _step(job_id, f"{t['period']} transcript has no text layer; skipped")
                        continue
                    doc_id = _save_doc(ticker, "transcript", t["period"], t["url"], pdf, pages)
                    claims = promise.extract_claims(ticker, name, t["period"], pages)
                    for c in claims:
                        c["source_url"] = t["url"]
                        c["doc_id"] = doc_id
                    all_claims += claims
                except Exception as e:
                    _step(job_id, f"{t['period']} transcript failed: {e}")
            _save_claims(ticker, all_claims)
        _step(job_id, "Checking promises against reported numbers…")
        tracker = promise.link_and_judge(all_claims, sc["quarters"], use_model=use_models)
        tracker.update({"id": "promise", "title": "Promise tracker",
                        "source": f"{len(tracker['calls'])} concall transcripts + exchange-reported quarterly numbers"})
        if not transcripts:
            tracker["empty_reason"] = "No concall transcripts listed for this company"
        elif not all_claims:
            tracker["empty_reason"] = "Transcripts not processed (no model key or no text layer)" if not llm.available("claims") else "No checkable guidance found in the transcripts"
        cards["promise"] = tracker

        # --- annual report: snapshot + exposures ---
        ars = sc["docs"]["annual_reports"]
        if ars and use_models and llm.available("snapshot"):
            ar = ars[0]
            _step(job_id, f"Reading {ar['period']} annual report…")
            try:
                pdf = screener.download_pdf(ar["url"])
                pages = screener.pdf_pages(pdf)
                doc_id = _save_doc(ticker, "annual_report", ar["period"], ar["url"], pdf, [])
                secs = _ar_sections(pages)
                text = "\n".join(f"[[page {n}]]\n{p}" for n, p in secs)[:120_000]
                if text:
                    snap = llm.call("snapshot", SNAPSHOT_PROMPT.format(name=name, text=text))
                    snap["key_facts"] = [k for k in snap.get("key_facts", []) if promise.quote_found(k.get("quote", ""), pages, k.get("page"))[0]]
                    cards["snapshot"] = {"id": "snapshot", "title": "Snapshot", **snap, "source": f"{ar['period']} annual report", "source_url": ar["url"]}
                    _step(job_id, "Mapping disclosed exposures…")
                    ex = llm.call("exposures", EXPOSURE_PROMPT.format(name=name, factors=", ".join(EXPOSURE_FACTORS), text=text))
                    _save_exposures(ticker, doc_id, [e for e in ex.get("exposures", [])
                                                     if e.get("factor") in EXPOSURE_FACTORS and promise.quote_found(e.get("quote", ""), pages, e.get("page"))[0]])
            except Exception as e:
                _step(job_id, f"Annual report failed: {e}")

        # --- bull vs bear over the cards ---
        if use_models and llm.available("bullbear"):
            _step(job_id, "Weighing bull and bear cases…")
            try:
                slim = {k: {kk: vv for kk, vv in v.items() if kk not in ("source_url",)} for k, v in cards.items()}
                bb = llm.call("bullbear", BULLBEAR_PROMPT.format(name=name, ids=", ".join(cards), cards=str(slim)[:40_000]))
                valid = set(cards)
                cards["bullbear"] = {"id": "bullbear", "title": "Bull vs bear",
                                     "bull": [p for p in bb.get("bull", []) if set(p.get("cites", [])) & valid][:3],
                                     "bear": [p for p in bb.get("bear", []) if set(p.get("cites", [])) & valid][:3],
                                     "source": "Derived only from the cards above"}
            except Exception as e:
                _step(job_id, f"Bull/bear failed: {e}")

        view = {"ticker": ticker, "name": name, "ratios": sc["ratios"], "cards": cards,
                "order": ["promise", "snapshot", "numbers", "cash", "bullbear", "balance"],
                "built_at": datetime.utcnow().isoformat()}
        with session_scope() as s:
            s.merge(Research(ticker=ticker, view=view, built_at=datetime.utcnow()))
            j = s.get(Job, job_id)
            j.status = "done"
            j.steps = [*j.steps, {"at": datetime.utcnow().isoformat(), "msg": "Done"}]
        return view
    except Exception as e:
        log.exception("research %s failed", ticker)
        with session_scope() as s:
            j = s.get(Job, job_id) or Job(id=job_id)
            j.status, j.error = "error", str(e)
            s.merge(j)
        raise


def _save_doc(ticker, kind, period, url, pdf: bytes, pages: list[str]) -> int:
    h = hashlib.sha256(pdf).hexdigest()
    with session_scope() as s:
        d = s.query(Document).filter_by(sha256=h).first()
        if not d:
            d = Document(ticker=ticker, kind=kind, period=period, url=url, sha256=h, pages=pages)
            s.add(d)
            s.flush()
        return d.id


def _save_claims(ticker: str, claims: list[dict]) -> None:
    with session_scope() as s:
        s.query(GuidanceClaim).filter_by(ticker=ticker).delete()
        for c in claims:
            s.add(GuidanceClaim(ticker=ticker, doc_id=c.get("doc_id", 0), call_period=c["call"], metric=c["metric"],
                                target_text=(c.get("target_text") or "")[:200], period=c.get("period") or "", kind=c.get("kind") or "",
                                quote=c.get("quote", ""), speaker=(c.get("speaker") or "")[:120], page=c.get("page") or 0, data=c))


def _save_exposures(ticker: str, doc_id: int, ex: list[dict]) -> None:
    with session_scope() as s:
        s.query(Exposure).filter_by(ticker=ticker).delete()
        for e in ex:
            s.add(Exposure(ticker=ticker, factor=e["factor"], direction=e.get("direction", "hurts"), strength=e.get("strength", "medium"),
                           quote=e.get("quote", ""), page=e.get("page") or 0, doc_id=doc_id))


def impact_tree(s: Session, factor: str, move_pct: float | None = None) -> dict:
    """event -> exposure -> holdings, one level, from disclosed exposures only."""
    from ..models import Holding

    held = {h.ticker: h for h in s.query(Holding).all()}
    edges = []
    for e in s.query(Exposure).filter(Exposure.factor == factor).all():
        if e.ticker not in held:
            continue
        sign = "+" if e.direction == "helps" else "−"
        if move_pct is not None and move_pct < 0:
            sign = "−" if sign == "+" else "+"
        doc = s.get(Document, e.doc_id)
        edges.append({"ticker": e.ticker, "name": held[e.ticker].name, "sign": sign, "strength": e.strength,
                      "quote": e.quote, "page": e.page, "source": f"{doc.period} annual report" if doc else "annual report",
                      "source_url": doc.url if doc else ""})
    order = {"high": 0, "medium": 1, "low": 2}
    edges.sort(key=lambda x: order.get(x["strength"], 3))
    seen: set[str] = set()
    edges = [e for e in edges if not (e["ticker"] in seen or seen.add(e["ticker"]))]  # strongest edge per holding
    return {"factor": factor, "move_pct": move_pct, "edges": edges,
            "note": "Disclosed exposures from each company's annual report. Not a forecast of impact size."}


def build_exposures(ticker: str) -> int:
    """Exposure graph only (no transcripts): annual report -> relevant sections -> one model call -> quote check."""
    sc = screener.company(ticker)
    ars = sc["docs"]["annual_reports"]
    if not ars:
        log.warning("%s: no annual report listed", ticker)
        return 0
    ar = ars[0]
    pdf = screener.download_pdf(ar["url"])
    pages = screener.pdf_pages(pdf)
    doc_id = _save_doc(ticker, "annual_report", ar["period"], ar["url"], pdf, [])
    secs = _ar_sections(pages)
    text = "\n".join(f"[[page {n}]]\n{p}" for n, p in secs)[:120_000]
    if not text:
        log.warning("%s: no MD&A / risk pages found (scanned PDF?)", ticker)
        return 0
    ex = llm.call("exposures", EXPOSURE_PROMPT.format(name=sc["name"] or ticker, factors=", ".join(EXPOSURE_FACTORS), text=text))
    keep = [e for e in ex.get("exposures", [])
            if e.get("factor") in EXPOSURE_FACTORS and promise.quote_found(e.get("quote", ""), pages, e.get("page"))[0]]
    _save_exposures(ticker, doc_id, keep)
    return len(keep)
