"""Watch rules: the brief's configurable alerts, generalised to anything FINN can check.

Spec shapes (all carry "type"):
  price   {type, scope, metric: "pct_change", op: "abs_gt"|"gt"|"lt", value}
  volume  {type, scope, metric: "vol_ratio_20d", op: "gt", value}
  filing  {type, scope, category}
  event   {type, ticker, event: "results_board_meeting", offset_days: -2}
  macro   {type, series: "CL=F", metric: "pct_change", op, value}
  all_of  {type, rules: [spec, spec]}
scope: "TICKER" | "portfolio" | "sector:<Sector>"
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ingest import MACRO
from .models import Event, Filing, Holding, Rule, RuleHit, Setting
from .score import CATEGORY_LABEL

OPS = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b, "abs_gt": lambda a, b: abs(a) > b}
CHECKABLE_CATEGORIES = set(CATEGORY_LABEL) - {"routine", "unclassified"}


class RuleError(ValueError):
    pass


def validate(spec: dict) -> dict:
    t = spec.get("type")
    if t in ("price", "volume", "macro"):
        if spec.get("op") not in OPS:
            raise RuleError("op must be gt, lt or abs_gt")
        try:
            spec["value"] = float(spec["value"])
        except (KeyError, TypeError, ValueError):
            raise RuleError("value must be a number")
        if t == "macro" and spec.get("series") not in MACRO:
            raise RuleError(f"FINN watches these macro series: {', '.join(MACRO.values())}")
        if t != "macro" and not spec.get("scope"):
            raise RuleError("scope is required")
        spec.setdefault("metric", "vol_ratio_20d" if t == "volume" else "pct_change")
    elif t == "filing":
        if spec.get("category") not in CHECKABLE_CATEGORIES:
            raise RuleError("unknown filing category")
        if not spec.get("scope"):
            raise RuleError("scope is required")
    elif t == "event":
        if not spec.get("ticker"):
            raise RuleError("ticker is required")
        spec.setdefault("event", "results_board_meeting")
        spec["offset_days"] = int(spec.get("offset_days", -1))
    elif t == "all_of":
        spec["rules"] = [validate(r) for r in spec.get("rules", [])]
        if len(spec["rules"]) < 2:
            raise RuleError("all_of needs two rules")
    else:
        raise RuleError("unknown rule type")
    return spec


def label(spec: dict) -> str:
    t = spec["type"]
    scope = spec.get("scope", "")
    where = "any holding" if scope == "portfolio" else (f"any {scope[7:]} stock" if scope.startswith("sector:") else scope)
    if t == "price":
        word = {"abs_gt": "moves more than", "gt": "rises more than", "lt": "falls more than"}[spec["op"]]
        v = abs(spec["value"])
        return f"{where} {word} {v:g}% in a day"
    if t == "volume":
        return f"{where} volume above {spec['value']:g}× its 20-day average"
    if t == "macro":
        word = {"abs_gt": "moves more than", "gt": "rises more than", "lt": "falls more than"}[spec["op"]]
        return f"{MACRO[spec['series']]} {word} {abs(spec['value']):g}% in a day"
    if t == "filing":
        return f"{CATEGORY_LABEL[spec['category']]} filing at {where}"
    if t == "event":
        n = -spec["offset_days"]
        return f"{n} day{'s' if n != 1 else ''} before {spec['ticker']} results" if n > 0 else f"On {spec['ticker']} results day"
    if t == "all_of":
        return " and ".join(label(r) for r in spec["rules"])
    return str(spec)


def scope_tickers(s: Session, scope: str) -> list[str]:
    if scope == "portfolio":
        return [h.ticker for h in s.scalars(select(Holding)).all()]
    if scope.startswith("sector:"):
        sec = scope[7:].lower()
        return [h.ticker for h in s.scalars(select(Holding)).all() if h.sector.lower() == sec]
    return [scope.upper()]


def _hit(s: Session, rule: Rule, key: str, message: str, payload: dict) -> RuleHit | None:
    if s.scalars(select(RuleHit).where(RuleHit.rule_id == rule.id, RuleHit.key == key)).first():
        return None
    h = RuleHit(rule_id=rule.id, key=key, message=message, payload=payload)
    s.add(h)
    s.flush()
    return h


def evaluate_eod(s: Session, day: date) -> list[RuleHit]:
    """Price, volume, macro and event-date rules. Run after 4 pm IST."""
    from .pipeline import day_move

    hits = []
    for rule in s.scalars(select(Rule).where(Rule.active.is_(True))).all():
        sp = rule.spec
        t = sp["type"]
        if t in ("price", "volume"):
            for tk in scope_tickers(s, sp["scope"]):
                mv = day_move(s, tk, day)
                val = mv.get("pct") if t == "price" else mv.get("vol_ratio")
                if val is None or not OPS[sp["op"]](val, sp["value"] if sp["op"] != "lt" else -abs(sp["value"])):
                    continue
                msg = f"{tk} {mv['pct']:+.1f}% on {mv.get('vol_ratio') or 0:.1f}× its 20-day volume"
                same_day = s.scalars(select(Filing).where(Filing.ticker == tk, Filing.filed_at >= datetime.combine(day, datetime.min.time()),
                                                          Filing.filed_at < datetime.combine(day + timedelta(days=1), datetime.min.time()), Filing.tier.in_(["S", "A", "B"]))).first()
                if same_day:
                    msg += f", same day as: {same_day.headline}"
                h = _hit(s, rule, f"{tk}:{day}", msg, {"ticker": tk, "move": mv, "filing_id": same_day.id if same_day else None})
                if h:
                    hits.append(h)
        elif t == "macro":
            mv = day_move(s, sp["series"], day)
            if mv and OPS[sp["op"]](mv["pct"], sp["value"] if sp["op"] != "lt" else -abs(sp["value"])):
                h = _hit(s, rule, f"{sp['series']}:{day}", f"{MACRO[sp['series']]} {mv['pct']:+.1f}% today",
                         {"series": sp["series"], "move": mv, "impact": True})
                if h:
                    hits.append(h)
        elif t == "event":
            for ev in s.scalars(select(Event).where(Event.ticker == sp["ticker"], Event.event == sp["event"])).all():
                if ev.day + timedelta(days=sp["offset_days"]) == day:
                    n = -sp["offset_days"]
                    h = _hit(s, rule, f"{ev.ticker}:{ev.day}", f"{ev.ticker} results board meeting in {n} day{'s' if n != 1 else ''} ({ev.day:%d %b})",
                             {"ticker": ev.ticker})
                    if h:
                        hits.append(h)
    return hits


def _filing_matches(s: Session, sp: dict, f: Filing) -> bool:
    return sp.get("category") == f.category and f.ticker in scope_tickers(s, sp["scope"])


def evaluate_filings(s: Session, filings: list[Filing]) -> list[RuleHit]:
    """Filing rules (and all_of built from them). Run on every announcements poll."""
    hits = []
    for rule in s.scalars(select(Rule).where(Rule.active.is_(True))).all():
        sp = rule.spec
        if sp["type"] == "filing":
            for f in filings:
                if _filing_matches(s, sp, f):
                    h = _hit(s, rule, f.id, f.headline or f"{f.ticker}: {f.subject}", {"ticker": f.ticker, "filing_id": f.id})
                    if h:
                        hits.append(h)
        elif sp["type"] == "all_of":
            # fires once every part has matched some filing since the rule was created
            done = []
            for part in sp["rules"]:
                if part["type"] != "filing":
                    done.append(False)
                    continue
                m = s.scalars(select(Filing).where(Filing.filed_at >= rule.created_at, Filing.category == part["category"])).all()
                done.append(any(_filing_matches(s, part, f) for f in m))
            if all(done):
                h = _hit(s, rule, "all", f"Done: {rule.label}", {})
                if h:
                    hits.append(h)
    return hits


def ensure_defaults(s: Session) -> None:
    """Install defaults once: 2× volume and ±5% price on every holding (+ S-tier pushes are always on)."""
    if s.scalars(select(Rule).where(Rule.source == "default")).first():
        return
    for spec in ({"type": "price", "scope": "portfolio", "metric": "pct_change", "op": "abs_gt", "value": 5},
                 {"type": "volume", "scope": "portfolio", "metric": "vol_ratio_20d", "op": "gt", "value": 2}):
        s.add(Rule(spec=spec, label=label(spec), source="default"))


# ---------------- natural language -> rule (rules first, model second) ----------------
_NUM = r"(\d+(?:\.\d+)?)"
_MACRO_WORDS = {"crude": "CL=F", "oil": "CL=F", "brent": "CL=F", "rupee": "USDINR=X", "usd": "USDINR=X",
                "dollar": "USDINR=X", "inr": "USDINR=X", "gold": "GC=F", "nifty": "^NSEI"}
_CAT_WORDS = [("transcript", "earnings_call"), ("concall", "earnings_call"), ("con call", "earnings_call"),
              ("management change", "management_change"), ("ceo", "management_change"), ("cfo", "management_change"),
              ("resign", "management_change"), ("rating", "credit_rating"), ("downgrade", "credit_rating"),
              ("pledge", "pledging"), ("dividend", "dividend"), ("acquisition", "M&A"), ("merger", "M&A"),
              ("results", "results"), ("order", "press_release"), ("fund raise", "fund_raise"), ("qip", "fund_raise"),
              ("insider", "insider_trading"), ("litigation", "litigation"), ("bonus", "bonus_split"), ("split", "bonus_split")]
_UNCHECKABLE = re.compile(r"sentiment|news|tweet|twitter|rumou?r|analyst (rating|target)|target price|social", re.I)


_TICKER_STOP = {"FINN", "NSE", "BSE", "EOD", "USD", "INR", "CEO", "CFO", "AGM", "EGM", "EBITDA", "PAT", "PBT", "QIP"}


def _clean_name(name: str) -> list[str]:
    return re.sub(r"\b(ltd|limited|industries|india|of|the|company|corporation|co)\b\.?", " ", name.lower()).split()


def resolve_tickers(s: Session, text: str) -> list[str]:
    """Match tickers, full names, or a name's first word when no other holding shares it ("Titan", "Infosys")."""
    low = text.lower()
    hs = s.scalars(select(Holding)).all()
    firsts: dict[str, int] = {}
    for h in hs:
        w = _clean_name(h.name)
        if w:
            firsts[w[0]] = firsts.get(w[0], 0) + 1
    aliases = (s.get(Setting, "aliases") or Setting(value={})).value
    found = []
    for h in hs:
        w = _clean_name(h.name)
        names = {h.ticker.lower(), " ".join(w), *[a.lower() for a in aliases.get(h.ticker, [])]}
        if w and firsts[w[0]] == 1:
            names.add(w[0])
        if len(w) >= 2:
            names.add(" ".join(w[:2]))
        if any(len(n) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(n)}('s)?(?![a-z0-9])", low) for n in names):
            found.append(h.ticker)
    if not found:
        found = [w for w in re.findall(r"\b[A-Z][A-Z&]{2,14}\b", text) if w not in _TICKER_STOP]
    return found


_SECTOR_STOP = {"private", "services", "capital", "goods", "marketing"}


def resolve_sector(s: Session, text: str) -> str | None:
    low = text.lower()
    for sec in sorted({h.sector for h in s.scalars(select(Holding)).all() if h.sector}):
        if sec.lower() in low:
            return sec
        for tok in sec.lower().split():
            if tok in _SECTOR_STOP:
                continue
            stem = tok.rstrip("s")
            if len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}s?\b", low):
                return sec
            if tok == "it" and re.search(r"\bIT\b", text):
                return sec
    return None


def parse_rule_text(s: Session, text: str) -> dict:
    """Returns {"spec": ..., "label": ...} or {"error": ..., "closest": spec|None}."""
    low = text.lower()
    tickers = resolve_tickers(s, text)
    sector = resolve_sector(s, text)
    scope = tickers[0] if tickers else (f"sector:{sector}" if sector else ("portfolio" if re.search(r"\b(my|any|portfolio|holdings?)\b", low) else None))

    if _UNCHECKABLE.search(low):
        closest = {"type": "filing", "scope": scope or "portfolio", "category": "press_release"} if scope else None
        return {"error": "FINN can't check sentiment or news — it watches prices, volume, macro moves and exchange filings.",
                "closest": validate(closest) if closest else None}

    spec = None
    num = re.search(_NUM + r"\s*(%|percent|per cent)", low)
    mult = re.search(_NUM + r"\s*(x|×|times)", low)
    macro = next((v for k, v in _MACRO_WORDS.items() if re.search(rf"\b{k}\b", low)), None)
    up = re.search(r"\b(rise|rises|jump|jumps|up|gain|gains|surge|above)\b", low)
    down = re.search(r"\b(fall|falls|drop|drops|down|crash|crashes|decline|declines|below)\b", low)
    op = "gt" if up and not down else ("lt" if down and not up else "abs_gt")

    if "volume" in low:
        v = float(mult.group(1)) if mult else (2.0 if "double" in low else 3.0 if "triple" in low else None)
        if v and scope:
            spec = {"type": "volume", "scope": scope, "op": "gt", "value": v}
    elif macro and num and not tickers:
        spec = {"type": "macro", "series": macro, "op": op, "value": float(num.group(1))}
    elif num and scope and re.search(r"move|moves|fall|falls|drop|rise|rises|jump|up|down|gain|crash|decline", low):
        spec = {"type": "price", "scope": scope, "op": op, "value": float(num.group(1))}
    elif re.search(r"before .*results|results .*in \d+ days|days? before", low) and tickers:
        d = re.search(r"(\d+)\s*days?", low)
        spec = {"type": "event", "ticker": tickers[0], "event": "results_board_meeting", "offset_days": -int(d.group(1)) if d else -1}
    else:
        cats = [c for w, c in _CAT_WORDS if w in low]
        if cats and scope:
            uniq = list(dict.fromkeys(cats))
            if len(uniq) >= 2 and " and " in low:
                spec = {"type": "all_of", "rules": [{"type": "filing", "scope": scope, "category": c} for c in uniq[:2]]}
            else:
                spec = {"type": "filing", "scope": scope, "category": uniq[0]}
    if spec is None:
        return {"error": "Couldn't turn that into a rule.", "closest": None}
    spec = validate(spec)
    return {"spec": spec, "label": label(spec)}


RULE_PROMPT = """Turn the investor's request into one watch rule as JSON, or {{"error": "why"}} if FINN can't check it.
FINN can only check: daily % price change, volume ÷ 20-day average, macro series daily % change
(CL=F crude, USDINR=X rupee, GC=F gold, ^NSEI Nifty), new exchange filings by category, and days before a results board meeting.
Categories: {cats}. Holdings: {holdings}.
Shapes: {{"type":"price","scope":"TICKER|portfolio|sector:<Sector>","op":"gt|lt|abs_gt","value":5}}
{{"type":"volume","scope":...,"op":"gt","value":2}} {{"type":"macro","series":"CL=F","op":"gt","value":3}}
{{"type":"filing","scope":...,"category":"..."}} {{"type":"event","ticker":"INFY","offset_days":-2}}
Request: "{text}" """


def parse_rule(s: Session, text: str) -> dict:
    res = parse_rule_text(s, text)
    if "spec" in res or res.get("closest"):
        return res
    from . import llm

    if not llm.available("intent"):
        return res
    holdings = ", ".join(f"{h.ticker} ({h.name}, {h.sector})" for h in s.scalars(select(Holding)).all())
    try:
        out = llm.call("intent", RULE_PROMPT.format(cats=", ".join(sorted(CHECKABLE_CATEGORIES)), holdings=holdings, text=text))
        if "error" in out:
            return {"error": out["error"], "closest": None}
        spec = validate(out)
        return {"spec": spec, "label": label(spec)}
    except Exception as e:
        return {"error": f"Couldn't turn that into a rule ({e}).", "closest": None}
