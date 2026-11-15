"""Promise tracker: what management guided in the last 4–6 calls vs what was delivered.

1. extract forward-looking claims per transcript (mid model, page-tagged text)
2. drop any claim whose quote isn't actually in the transcript
3. link the same metric+period across calls -> revisions
4. look up the actual from screener's reported numbers
5. verdict: number claims by rules; direction claims by the strong model (or rules if no key)
"""
from __future__ import annotations

import logging
import re

from .. import llm
from .periods import call_to_results_quarter, fq_to_label, parse_period, prev_year

log = logging.getLogger("finn.promise")

METRICS = {
    "revenue_growth_yoy": "Revenue growth YoY (%)",
    "revenue_growth_cc": "Revenue growth, constant currency (%)",
    "ebitda_margin": "EBITDA / operating margin (%)",
    "ebit_margin": "EBIT margin (%)",
    "pat_growth_yoy": "Net profit growth YoY (%)",
    "ebitda_growth_yoy": "EBITDA growth YoY (%)",
    "gross_npa": "Gross NPA (%)",
    "other": "Other",
}

CLAIMS_PROMPT = """Below is an earnings-call transcript of {company} (NSE: {ticker}). The call was held in {call_label}
and discussed {results_q} results. Pages are marked [[page N]].
Extract every FORWARD-LOOKING statement made by management (not analysts) about a measurable business outcome:
guidance, targets, expectations, commitments. Ignore safe-harbour boilerplate.
Use ONLY this transcript. Copy the quote EXACTLY as it appears (one or two sentences, max 40 words).
Normalise:
- metric: one of {metrics} (use "other" and describe it in metric_text when nothing fits)
- period: Q<n>FY<yy> | H<n>FY<yy> | FY<yy> (e.g. "next year" said in {call_label} = the next fiscal year). null if no period.
- kind: "number" if there is a numeric target, else "direction" (e.g. "margins will improve")
- comparator: "at_least" | "at_most" | "range" | "about" (number claims only)
- target_low / target_high: numbers in the metric's unit (for "about 15%" low=high=15). null for direction claims.
- direction: "up" | "down" | "stable" (direction claims only)
Return JSON: {{"claims": [{{"metric": "", "metric_text": "", "target_text": "how it was said, e.g. 'double-digit growth'",
 "period": "", "kind": "", "comparator": null, "target_low": null, "target_high": null, "direction": null,
 "quote": "", "speaker": "", "page": 0}}]}}

{text}"""

VERDICT_PROMPT = """Judge whether management delivered on this statement, using ONLY the reported numbers given.
Statement ({call_label} call, page {page}): "{quote}"
Claim: {metric_text} — {direction} — for {period}.
Reported numbers (₹ crore unless %): {actuals}
Verdicts: Delivered | Partly | Missed | Pending (period not over) | Can't verify (numbers don't cover it).
Return JSON: {{"verdict": "", "reasoning": "max 2 sentences, cite the numbers"}}"""


# ---------------- quote check ----------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", (s or "").lower()).strip()


def quote_found(quote: str, pages: list[str], page_hint: int | None = None) -> tuple[bool, int]:
    """True if ≥80% of the quote's 6-word chunks occur in the transcript. Returns (found, page)."""
    q = _norm(quote).split()
    if len(q) < 4:
        return False, 0
    chunks = [" ".join(q[i : i + 6]) for i in range(0, max(1, len(q) - 5), 3)] or [" ".join(q)]
    order = list(range(len(pages)))
    if page_hint and 1 <= page_hint <= len(pages):
        order.sort(key=lambda i: abs(i - (page_hint - 1)))
    full = _norm(" ".join(pages))
    hits = sum(1 for c in chunks if c in full)
    if hits / len(chunks) < 0.8:
        return False, 0
    for i in order:  # locate the page (quote may span a page break; take first chunk's page)
        if chunks[0] in _norm(pages[i]):
            return True, i + 1
    return True, page_hint or 0


# ---------------- actuals from screener ----------------
def _q_values(quarters: dict, row_names: tuple[str, ...]) -> dict[tuple[int, int], float]:
    from .periods import label_to_fq

    rows = quarters.get("rows", {})
    row = next((rows[n] for n in row_names if n in rows), None)
    if row is None:
        return {}
    out = {}
    for lbl, v in zip(quarters.get("periods", []), row):
        fq = label_to_fq(lbl)
        if fq and v is not None:
            out[fq] = v
    return out


def actual_for(metric: str, period: str, quarters: dict) -> dict:
    """Returns {"status": "ok"|"pending"|"unverifiable", "value", "detail", "approx"}."""
    p = parse_period(period or "")
    if not p:
        return {"status": "unverifiable", "detail": "no period"}
    sales = _q_values(quarters, ("Sales", "Revenue"))
    op = _q_values(quarters, ("Operating Profit", "Financing Profit"))
    dep = _q_values(quarters, ("Depreciation",))
    pat = _q_values(quarters, ("Net Profit",))
    npa = _q_values(quarters, ("Gross NPA %",))
    if not sales:
        return {"status": "unverifiable", "detail": "no quarterly numbers"}
    latest = max(sales)
    need = p["quarters"]
    if any(q > latest for q in need):
        done = [q for q in need if q <= latest]
        return {"status": "pending", "detail": f"{len(done)} of {len(need)} quarters reported"}

    def tot(series, qs):
        vals = [series.get(q) for q in qs]
        return None if any(v is None for v in vals) else sum(vals)

    prev = prev_year(need)
    approx = False
    if metric in ("revenue_growth_yoy", "revenue_growth_cc"):
        a, b = tot(sales, need), tot(sales, prev)
        approx = metric == "revenue_growth_cc"
        val = (a / b - 1) * 100 if a and b else None
        detail = f"revenue ₹{a:,.0f} cr vs ₹{b:,.0f} cr" if val is not None else ""
    elif metric == "pat_growth_yoy":
        a, b = tot(pat, need), tot(pat, prev)
        val = (a / b - 1) * 100 if a and b and b > 0 else None
        detail = f"PAT ₹{a:,.0f} cr vs ₹{b:,.0f} cr" if val is not None else ""
    elif metric == "ebitda_growth_yoy":
        a, b = tot(op, need), tot(op, prev)
        val = (a / b - 1) * 100 if a and b and b > 0 else None
        detail = f"operating profit ₹{a:,.0f} cr vs ₹{b:,.0f} cr" if val is not None else ""
    elif metric == "ebitda_margin":
        a, r = tot(op, need), tot(sales, need)
        val = a / r * 100 if a is not None and r else None
        detail = "operating profit ÷ sales"
    elif metric == "ebit_margin":
        a, d, r = tot(op, need), tot(dep, need), tot(sales, need)
        val = (a - d) / r * 100 if None not in (a, d) and r else None
        detail = "(operating profit − depreciation) ÷ sales"
    elif metric == "gross_npa" and npa:
        val = npa.get(need[-1])
        detail = "gross NPA % at period end"
    else:
        return {"status": "unverifiable", "detail": "metric not in reported numbers"}
    if val is None:
        return {"status": "unverifiable", "detail": "numbers missing for that period"}
    return {"status": "ok", "value": round(val, 1), "detail": detail, "approx": approx,
            "quarters": [fq_to_label(*q) for q in need]}


def number_verdict(c: dict, actual: dict) -> tuple[str, str]:
    if actual["status"] == "pending":
        return "Pending", actual["detail"]
    if actual["status"] != "ok":
        return "Can't verify", actual["detail"]
    v, lo, hi, comp = actual["value"], c.get("target_low"), c.get("target_high"), c.get("comparator") or "about"
    if lo is None and hi is None:
        return "Can't verify", "no numeric target"
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    tol = max(1.0, abs(lo) * 0.1)
    note = f"actual {v:g}% ({actual['detail']})" + (" — INR, not constant currency" if actual.get("approx") else "")
    if comp == "at_most":
        if v <= hi:
            return "Delivered", note
        return ("Partly" if v <= hi + tol else "Missed"), note
    if v >= lo:
        return "Delivered", note
    return ("Partly" if v >= lo - tol else "Missed"), note


def direction_verdict_rules(c: dict, actual_start: dict, actual_end: dict) -> tuple[str, str]:
    if actual_end["status"] == "pending":
        return "Pending", actual_end["detail"]
    if actual_end["status"] != "ok" or actual_start.get("status") != "ok":
        return "Can't verify", actual_end.get("detail", "")
    a, b = actual_start["value"], actual_end["value"]
    d = c.get("direction") or "up"
    moved = b - a
    note = f"{a:g}% → {b:g}%"
    if d == "up":
        return ("Delivered" if moved > 0.2 else "Partly" if moved > -0.2 else "Missed"), note
    if d == "down":
        return ("Delivered" if moved < -0.2 else "Partly" if moved < 0.2 else "Missed"), note
    return ("Delivered" if abs(moved) <= 1 else "Missed"), note


# ---------------- pipeline ----------------
def tag_pages(pages: list[str]) -> str:
    return "\n".join(f"[[page {i}]]\n{p}" for i, p in enumerate(pages, 1))


def extract_claims(ticker: str, company: str, call_label: str, pages: list[str]) -> list[dict]:
    rq = call_to_results_quarter(call_label)
    out = llm.call("claims", CLAIMS_PROMPT.format(
        company=company, ticker=ticker, call_label=call_label,
        results_q=f"Q{rq[1]}FY{rq[0]}" if rq else "the latest quarter's",
        metrics=", ".join(METRICS), text=tag_pages(pages)[:180_000]))
    kept = []
    for c in out.get("claims", []):
        found, page = quote_found(c.get("quote", ""), pages, c.get("page"))
        if not found:
            log.info("dropped unmatched claim: %s", c.get("quote", "")[:80])
            continue
        c["page"] = page
        c["call"] = call_label
        if c.get("metric") not in METRICS:
            c["metric"] = "other"
        kept.append(c)
    return kept


def link_and_judge(claims: list[dict], quarters: dict, use_model: bool = True) -> dict:
    """claims from all calls (oldest call first) -> tracker rows + scorecard."""
    from .periods import label_to_fq

    def call_key(c):
        rq = call_to_results_quarter(c["call"]) or (0, 0)
        return rq

    claims = sorted(claims, key=call_key)
    groups: dict[str, list[dict]] = {}
    for c in claims:
        key = f"{c['metric']}|{(c.get('period') or '').upper()}" if c["metric"] != "other" else f"other|{_norm(c.get('metric_text', ''))[:40]}|{c.get('period')}"
        groups.setdefault(key, []).append(c)

    rows = []
    for key, cs in groups.items():
        latest = cs[-1]
        history = [{"call": c["call"], "said": c.get("target_text"), "page": c.get("page")} for c in cs]
        revised = len({(c.get("target_low"), c.get("target_high"), c.get("direction")) for c in cs}) > 1
        metric = latest["metric"]
        if latest.get("kind") == "number":
            verdict, reason = number_verdict(latest, actual_for(metric, latest.get("period"), quarters))
        else:
            end = actual_for(metric, latest.get("period"), quarters) if metric != "other" else {"status": "unverifiable"}
            rq = call_key(cs[0])
            start = actual_for(metric, f"Q{rq[1]}FY{rq[0]}", quarters) if rq != (0, 0) and metric != "other" else {"status": "unverifiable"}
            verdict, reason = direction_verdict_rules(latest, start, end)
            if verdict == "Can't verify" and use_model and llm.available("verdict") and latest.get("period"):
                p = parse_period(latest.get("period"))
                if p and quarters.get("periods") and max(label_to_fq(x) or (0, 0) for x in quarters["periods"]) < p["quarters"][-1]:
                    verdict, reason = "Pending", "period not over"
                else:
                    try:
                        snap = {k: dict(zip(quarters["periods"][-8:], v[-8:])) for k, v in quarters["rows"].items()
                                if k in ("Sales", "Revenue", "Operating Profit", "OPM %", "Net Profit", "Financing Profit", "Gross NPA %")}
                        out = llm.call("verdict", VERDICT_PROMPT.format(
                            call_label=latest["call"], page=latest.get("page"), quote=latest["quote"],
                            metric_text=latest.get("metric_text") or METRICS.get(metric, metric),
                            direction=latest.get("direction") or "", period=latest.get("period"), actuals=snap))
                        if out.get("verdict") in ("Delivered", "Partly", "Missed", "Pending", "Can't verify"):
                            verdict, reason = out["verdict"], out.get("reasoning", "")
                    except Exception as e:
                        log.warning("verdict model failed: %s", e)
        rows.append({
            "key": key, "metric": metric, "metric_label": latest.get("metric_text") or METRICS.get(metric, metric),
            "period": latest.get("period"), "said": latest.get("target_text"), "kind": latest.get("kind"),
            "verdict": verdict, "delivered": reason, "revised": revised, "history": history,
            "quote": latest.get("quote"), "speaker": latest.get("speaker"), "call": latest["call"], "page": latest.get("page"),
            "source_url": latest.get("source_url"),
        })
    order = {"Missed": 0, "Partly": 1, "Delivered": 2, "Pending": 3, "Can't verify": 4}
    rows.sort(key=lambda r: (order.get(r["verdict"], 5), r["metric"]))
    judged = [r for r in rows if r["verdict"] in ("Delivered", "Partly", "Missed")]
    delivered = sum(1 for r in judged if r["verdict"] == "Delivered")
    return {"scorecard": {"delivered": delivered, "judged": len(judged), "total": len(rows),
                          "text": f"{delivered} of {len(judged)} promises delivered" if judged else "No promises can be judged yet"},
            "rows": rows, "calls": sorted({c["call"] for c in claims}, key=lambda x: call_to_results_quarter(x) or (0, 0))}
