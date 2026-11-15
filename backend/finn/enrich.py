"""Enrichment for S and A items only: results table, management-change bio, one-line summaries.
Every model output is checked (arithmetic for results, string presence for bios) before it's shown."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from . import llm

log = logging.getLogger("finn.enrich")

GROUNDING = ("Use ONLY the document provided. Do not use outside knowledge. If a value is not in the "
             "document, use null. Numbers as plain floats without commas.")


# ---------------- results ----------------
RESULTS_PROMPT = """You are reading an Indian listed company's quarterly financial results filing.
Extract the CONSOLIDATED statement if present, otherwise standalone. {grounding}
Return JSON:
{{"period": "Q2 FY27", "unit": "₹ crore" | "₹ lakh" | "₹ million", "basis": "consolidated"|"standalone",
  "is_bank": true|false,
  "columns": {{"current": {{...}}, "prev_quarter": {{...}}, "year_ago": {{...}}}},
  "page": <page number of the table>}}
Each column object has keys: revenue (revenue from operations; for banks total interest earned),
other_income, total_income, total_expenses, finance_cost, depreciation, pbt (profit before tax),
pat (net profit for the period attributable to owners if shown, else net profit),
nii (banks: net interest income, else null), ppop (banks: operating profit before provisions, else null),
gnpa_pct (banks: gross NPA %, else null)."""


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a - b) / abs(b) * 100, 1)


def _ebitda(col: dict):
    need = ("pbt", "finance_cost", "depreciation", "other_income")
    if any(col.get(k) is None for k in need):
        return None
    return col["pbt"] + col["finance_cost"] + col["depreciation"] - col["other_income"]


def build_results_card(raw: dict, screener_q: dict | None = None) -> dict:
    """raw = model JSON (or screener-derived). Adds derived EBITDA, QoQ/YoY, checks."""
    cols = raw.get("columns", {})
    cur, pq, yq = cols.get("current", {}), cols.get("prev_quarter", {}), cols.get("year_ago", {})
    is_bank = bool(raw.get("is_bank"))
    metrics = ["revenue", "nii", "ppop", "pat", "gnpa_pct"] if is_bank else ["revenue", "ebitda", "pbt", "pat"]
    for c in (cur, pq, yq):
        if not is_bank and c.get("ebitda") is None:
            c["ebitda"] = _ebitda(c)
    card: dict = {"period": raw.get("period", ""), "unit": raw.get("unit", "₹ crore"), "basis": raw.get("basis", ""),
                  "is_bank": is_bank, "rows": [], "checks": [], "page": raw.get("page")}
    for m in metrics:
        row = {"metric": m, "q": cur.get(m), "pq": pq.get(m), "yq": yq.get(m),
               "qoq_pct": _pct(cur.get(m), pq.get(m)), "yoy_pct": _pct(cur.get(m), yq.get(m)),
               "derived": m == "ebitda" and cols.get("current", {}).get("ebitda_reported") is None}
        card["rows"].append(row)
        card[m] = row
    if not is_bank and cur.get("ebitda") and cur.get("revenue"):
        card["ebitda_margin"] = {"q": round(cur["ebitda"] / cur["revenue"] * 100, 1),
                                 "pq": round(pq["ebitda"] / pq["revenue"] * 100, 1) if pq.get("ebitda") and pq.get("revenue") else None,
                                 "yq": round(yq["ebitda"] / yq["revenue"] * 100, 1) if yq.get("ebitda") and yq.get("revenue") else None}
    # Arithmetic check: PBT ≈ total income − total expenses (exceptional items can break this)
    ok = True
    ti, te, pbt = cur.get("total_income"), cur.get("total_expenses"), cur.get("pbt")
    if None not in (ti, te, pbt) and pbt:
        gap = abs((ti - te) - pbt) / abs(pbt)
        passed = gap < 0.03
        card["checks"].append({"name": "PBT = income − expenses", "ok": passed, "gap_pct": round(gap * 100, 1)})
        ok &= passed or gap < 0.15  # exceptional items: warn, don't fail
    if cur.get("pat") is not None and pbt is not None and cur["pat"] > pbt * 1.5 and pbt > 0:
        card["checks"].append({"name": "PAT ≤ PBT", "ok": False})
        ok = False
    if screener_q and cur.get("revenue") and screener_q.get("revenue"):
        gap = abs(cur["revenue"] - screener_q["revenue"]) / abs(screener_q["revenue"])
        card["checks"].append({"name": "matches screener revenue", "ok": gap < 0.03, "gap_pct": round(gap * 100, 1)})
        ok &= gap < 0.03
    card["verified"] = ok
    return card


def extract_results(pdf: bytes, screener_q: dict | None = None) -> dict:
    raw = llm.call("results", RESULTS_PROMPT.format(grounding=GROUNDING), pdf=pdf)
    return build_results_card(raw, screener_q)


def results_from_screener(quarters: dict) -> dict:
    """No-model fallback: build the results card from screener's quarterly table.
    quarters = parsed table {"periods": [...], "rows": {"Sales": [...], ...}} (see research.screener)."""
    periods, rows = quarters["periods"], quarters["rows"]
    if len(periods) < 5:
        return {}

    def col(i):
        g = lambda *names: next((rows[n][i] for n in names if n in rows and rows[n][i] is not None), None)  # noqa: E731
        is_bank = "Financing Profit" in rows
        rev = g("Sales", "Revenue")
        out = {"revenue": rev, "other_income": g("Other Income"), "finance_cost": g("Interest"),
               "depreciation": g("Depreciation"), "pbt": g("Profit before tax"), "pat": g("Net Profit")}
        if is_bank:
            out["nii"] = (rev - g("Interest")) if rev is not None and g("Interest") is not None else None
            out["ppop"] = g("Financing Profit")
        else:
            out["ebitda"] = g("Operating Profit")
            out["ebitda_reported"] = out["ebitda"]
        return out

    from .research.periods import label_to_fq

    fq = label_to_fq(periods[-1])
    raw = {"period": f"Q{fq[1]} FY{fq[0]}" if fq else periods[-1], "unit": "₹ crore", "basis": "screener", "is_bank": "Financing Profit" in rows,
           "columns": {"current": col(-1), "prev_quarter": col(-2), "year_ago": col(-5)}}
    card = build_results_card(raw)
    card["source"] = "screener.in quarterly table"
    return card


# ---------------- management change bio ----------------
BIO_PROMPT = """This is an Indian listed company's filing about a change in directors or key managerial personnel.
SEBI requires appointment filings to include a brief profile of the appointee. {grounding}
Return JSON: {{"left": [{{"name": "", "role": ""}}],
 "joined": [{{"name": "", "role": "", "effective_date": "YYYY-MM-DD or null", "bio": "max 3 short lines, from the brief profile only", "bio_quote": "exact sentence from the document the bio is based on"}}],
 "reason": "reason for leaving if stated, else null"}}
Filing text:
{text}"""


def extract_bio(text: str, pdf: bytes | None = None) -> dict:
    out = llm.call("bio", BIO_PROMPT.format(grounding=GROUNDING, text=text[:12000]), pdf=pdf)
    source_text = _norm(text)
    for j in out.get("joined", []) or []:
        q = _norm(j.get("bio_quote") or "")
        j["bio_verified"] = bool(q) and (q[:80] in source_text or not source_text)
        if not j.get("bio"):
            j["bio"] = None  # app shows "No profile in filing"; web lookup is a later fallback
    return out


# ---------------- one-liners (batched) ----------------
SUMMARY_PROMPT = """For each Indian stock-exchange filing below write a card. {grounding}
Rules: headline ≤ 70 characters, starts with the company short name, says what happened, numbers over adjectives.
summary ≤ 160 characters, one sentence, only facts from the text. Also extract any of these fields if present:
amount_cr (₹ crore, number), counterparty, rating_old, rating_new, agency, outlook, ratio, record_date, per_share.
Return JSON: {{"items": [{{"id": "...", "headline": "...", "summary": "...", "fields": {{}}}}]}}
Filings:
{items}"""


def summarise(filings: list[dict]) -> dict[str, dict]:
    """filings: [{id, company, subject, text}] -> {id: {headline, summary, fields}}. Batches of 8."""
    out: dict[str, dict] = {}
    for i in range(0, len(filings), 8):
        batch = filings[i : i + 8]
        items = "\n".join(f"- id={f['id']} | {f['company']} | {f['subject']} | {f['text'][:700]}" for f in batch)
        try:
            res = llm.call("summary", SUMMARY_PROMPT.format(grounding=GROUNDING, items=items))
            for it in res.get("items", []):
                out[str(it.get("id"))] = it
        except Exception as e:
            log.warning("summary batch failed: %s", e)
    return out


_BOILER = re.compile(r"^.*?\b(?:limited|ltd\.?)\s+(?:has\s+)?(?:(?:informed|intimated)\s+the\s+exchange\s*(?:about|regarding|that|of)?|submitted\s+(?:to\s+)?the\s+exchange,?|disclosed\s+that|submitted|filed|approved|received)\s*", re.I)


def fallback_headline(company: str, subject: str, text: str) -> tuple[str, str]:
    """No-model headline: NSE's own one-line summary minus the "X Limited has informed the Exchange" boilerplate."""
    short = re.sub(r"\s+(limited|ltd\.?)$", "", company, flags=re.I).strip() or company
    body = re.sub(r"\s+", " ", text or "").strip()
    gist = _BOILER.sub("", body).strip(" .,'\"") if body else ""
    gist = re.sub(r"^.{0,80}?\b(?:limited|ltd\.?)\s+(?:has\s+)?", "", gist, count=1, flags=re.I) if re.match(r"^.{0,80}?\b(?:limited|ltd\.?)\s", gist, re.I) else gist
    if gist and len(gist) > 12:
        gist = gist[0].upper() + gist[1:]
        head = f"{short}: {gist}"
        head = head if len(head) <= 95 else head[:94].rsplit(" ", 1)[0] + "…"
    else:
        head = f"{short}: {subject}"[:95]
    return head, (body[:157] + "…") if len(body) > 160 else body


# ---------------- events (results board meeting dates) ----------------
_DATE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\-/]*(\d{4})", re.I)
_MON = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def board_meeting_date(text: str) -> date | None:
    if not re.search(r"results?", text, re.I):
        return None
    m = _DATE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), _MON[m.group(2).lower()[:3]], int(m.group(1)))
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%.]+", " ", (s or "").lower()).strip()


def now_iso() -> str:
    return datetime.utcnow().isoformat()
