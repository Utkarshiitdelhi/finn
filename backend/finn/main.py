"""FastAPI app: /feed, /filing, /alerts, /company, /rules, /assistant, /push, /impact."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import assistant, config, llm, rules
from .db import get_db, init_db
from .feed import card, feed
from .models import Filing, Holding, Job, LlmLog, PushToken, Research, Rule, RuleHit, Setting
from .research import view as research

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
app = FastAPI(title="FINN API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup() -> None:
    init_db()
    from .db import session_scope
    from .pipeline import load_portfolio_file

    with session_scope() as s:
        if not s.scalars(select(Holding)).first() and config.PORTFOLIO_PATH.exists():
            load_portfolio_file(s)
        rules.ensure_defaults(s)


@app.get("/health")
def health():
    return {"ok": True, "models": {"gemini": bool(config.GEMINI_API_KEY), "groq": bool(config.GROQ_API_KEY)}, "at": datetime.utcnow().isoformat()}


# ---------------- push side ----------------
@app.get("/feed")
def get_feed(window: str = "24h", hours: int | None = None, db: Session = Depends(get_db)):
    return feed(db, window, hours)


@app.get("/filing/{fid}")
def get_filing(fid: str, db: Session = Depends(get_db)):
    f = db.get(Filing, fid)
    if not f:
        raise HTTPException(404, "filing not found")
    return card(f, full=True)


@app.post("/filing/{fid}/{action}")
def filing_action(fid: str, action: str, db: Session = Depends(get_db)):
    f = db.get(Filing, fid)
    if not f:
        raise HTTPException(404)
    if action == "dismiss":
        f.dismissed = True
    elif action == "pin":
        f.pinned = not f.pinned
    else:
        raise HTTPException(400, "action must be dismiss or pin")
    return {"ok": True, "pinned": f.pinned, "dismissed": f.dismissed}


@app.get("/alerts")
def alerts(days: int = 7, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    hits = db.scalars(select(RuleHit).where(RuleHit.hit_at >= since).order_by(RuleHit.hit_at.desc()).limit(50)).all()
    labels = {r.id: r.label for r in db.scalars(select(Rule)).all()}
    return [{"id": h.id, "rule_id": h.rule_id, "rule": labels.get(h.rule_id, ""), "message": h.message,
             "payload": h.payload, "at": h.hit_at.isoformat()} for h in hits]


# ---------------- rules ----------------
class RuleIn(BaseModel):
    spec: dict
    source: str = "form"


class TextIn(BaseModel):
    text: str
    ctx: dict = {}


def _rule_out(r: Rule, last_hit: RuleHit | None = None) -> dict:
    return {"id": r.id, "spec": r.spec, "label": r.label, "source": r.source, "active": r.active,
            "created_at": r.created_at.isoformat(), "last_hit": {"message": last_hit.message, "at": last_hit.hit_at.isoformat()} if last_hit else None}


@app.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(Rule).order_by(Rule.created_at.desc())).all():
        last = db.scalars(select(RuleHit).where(RuleHit.rule_id == r.id).order_by(RuleHit.hit_at.desc())).first()
        out.append(_rule_out(r, last))
    return out


@app.post("/rules/parse")
def parse_rule(body: TextIn, db: Session = Depends(get_db)):
    return rules.parse_rule(db, body.text)


@app.post("/rules")
def create_rule(body: RuleIn, db: Session = Depends(get_db)):
    try:
        spec = rules.validate(dict(body.spec))
    except rules.RuleError as e:
        raise HTTPException(400, str(e))
    r = Rule(spec=spec, label=rules.label(spec), source=body.source)
    db.add(r)
    db.flush()
    return _rule_out(r)


@app.patch("/rules/{rid}")
def toggle_rule(rid: int, active: bool, db: Session = Depends(get_db)):
    r = db.get(Rule, rid)
    if not r:
        raise HTTPException(404)
    r.active = active
    return _rule_out(r)


@app.delete("/rules/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db)):
    r = db.get(Rule, rid)
    if r:
        db.delete(r)
    return {"ok": True}


# ---------------- pull side ----------------
@app.get("/company/{ticker}")
def company(ticker: str, bg: BackgroundTasks, build: bool = True, db: Session = Depends(get_db)):
    ticker = ticker.upper()
    r = db.get(Research, ticker)
    if r:
        h = db.get(Holding, ticker)
        recent = db.scalars(select(Filing).where(Filing.ticker == ticker).order_by(Filing.filed_at.desc()).limit(10)).all()
        return {"status": "ready", "view": r.view, "holding": {"weight": h.weight, "sector": h.sector} if h else None,
                "filings": [card(f) for f in recent], "prices": _prices(db, ticker)}
    job = db.get(Job, f"research:{ticker}")
    if job and job.status == "running" and job.updated_at > datetime.utcnow() - timedelta(minutes=10):
        return {"status": "building", "steps": job.steps}
    if job and job.status == "error" and not build:
        return {"status": "error", "error": job.error, "steps": job.steps}
    if build:
        db.merge(Job(id=f"research:{ticker}", status="running", steps=[{"at": datetime.utcnow().isoformat(), "msg": "Queued…"}], error=""))
        db.commit()
        bg.add_task(research.build, ticker)
        return {"status": "building", "steps": [{"msg": "Queued…"}]}
    return {"status": "missing"}


def _prices(db: Session, ticker: str) -> list[dict]:
    from .models import Price

    rows = db.scalars(select(Price).where(Price.symbol == ticker).order_by(Price.day.desc()).limit(60)).all()
    return [{"day": p.day.isoformat(), "close": p.close} for p in reversed(rows)]


@app.get("/jobs/{jid:path}")
def job(jid: str, db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404)
    return {"id": j.id, "status": j.status, "steps": j.steps, "error": j.error}


@app.get("/impact/{series:path}")
def impact(series: str, move: float | None = None, db: Session = Depends(get_db)):
    factor = research.FACTOR_SERIES.get(series, series)
    if not factor:
        raise HTTPException(404, "no exposure map for that series")
    if move is None:
        from .pipeline import day_move
        from .models import Price

        last = db.scalars(select(Price).where(Price.symbol == series).order_by(Price.day.desc())).first()
        move = day_move(db, series, last.day).get("pct") if last else None
    return research.impact_tree(db, factor, move)


@app.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    ql = q.strip().lower()
    hs = db.scalars(select(Holding)).all()
    hits = [{"ticker": h.ticker, "name": h.name, "held": True} for h in hs if ql in h.ticker.lower() or ql in h.name.lower()]
    cached = db.scalars(select(Research)).all()
    hits += [{"ticker": r.ticker, "name": r.view.get("name", ""), "held": False} for r in cached
             if (ql in r.ticker.lower() or ql in r.view.get("name", "").lower()) and r.ticker not in {h["ticker"] for h in hits}]
    if q.strip().isalnum() and q.upper() not in {h["ticker"] for h in hits}:
        hits.append({"ticker": q.strip().upper(), "name": "Research any NSE ticker", "held": False})
    return hits[:10]


# ---------------- portfolio ----------------
@app.get("/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    prefs = (db.get(Setting, "prefs") or Setting(value={})).value
    return {"holdings": [{"ticker": h.ticker, "name": h.name, "sector": h.sector, "weight": h.weight, "starred": h.starred}
                         for h in db.scalars(select(Holding).order_by(Holding.weight.desc())).all()],
            "prefs": prefs}


class PrefsIn(BaseModel):
    starred_categories: list[str] | None = None
    price_pct: float | None = None
    vol_ratio: float | None = None


@app.put("/portfolio/prefs")
def put_prefs(body: PrefsIn, db: Session = Depends(get_db)):
    st = db.get(Setting, "prefs") or Setting(key="prefs", value={})
    st.value = {**st.value, **body.model_dump(exclude_none=True)}
    db.merge(st)
    # keep default rules in sync with the thresholds
    for r in db.scalars(select(Rule).where(Rule.source == "default")).all():
        sp = dict(r.spec)
        if sp["type"] == "price" and body.price_pct is not None:
            sp["value"] = body.price_pct
        if sp["type"] == "volume" and body.vol_ratio is not None:
            sp["value"] = body.vol_ratio
        r.spec, r.label = sp, rules.label(sp)
    return st.value


@app.post("/portfolio/star/{ticker}")
def star(ticker: str, db: Session = Depends(get_db)):
    h = db.get(Holding, ticker.upper())
    if not h:
        raise HTTPException(404)
    h.starred = not h.starred
    return {"ticker": h.ticker, "starred": h.starred}


# ---------------- assistant ----------------
@app.post("/assistant")
def ask(body: TextIn, db: Session = Depends(get_db)):
    try:
        return assistant.route(db, body.text, body.ctx)
    except llm.LLMUnavailable as e:
        return {"intent": "error", "say": "The model is busy; try again in a minute.", "detail": str(e)}


@app.post("/assistant/voice")
async def voice(audio: UploadFile = File(...), ctx: str = Form("{}"), db: Session = Depends(get_db)):
    data = await audio.read()
    try:
        text = llm.transcribe(data, audio.filename or "voice.m4a")
    except Exception as e:
        raise HTTPException(503, f"speech-to-text failed: {e}")
    out = assistant.route(db, text, json.loads(ctx or "{}"))
    out["heard"] = text
    return out


# ---------------- push ----------------
class TokenIn(BaseModel):
    token: str
    platform: str = "android"


@app.post("/push/register")
def register(body: TokenIn, db: Session = Depends(get_db)):
    db.merge(PushToken(token=body.token, platform=body.platform))
    return {"ok": True}


@app.post("/push/test")
def push_test(db: Session = Depends(get_db)):
    from .push import send

    f = db.scalars(select(Filing).where(Filing.tier == "S").order_by(Filing.filed_at.desc())).first()
    msg = {"title": f.headline if f else "FINN test", "body": (f.summary if f else "Push works."),
           "data": {"url": f"/filing/{f.id}" if f else "/"}}
    return {"sent": send(db, [msg])}


# ---------------- admin / cost ----------------
@app.post("/admin/run/{name}")
def run_job(name: str, bg: BackgroundTasks, x_admin_token: str = Header("")):
    if x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(403)
    from jobs import run

    if name not in run.JOBS:
        raise HTTPException(404, f"jobs: {list(run.JOBS)}")
    bg.add_task(run.JOBS[name])
    return {"started": name}


@app.get("/stats/cost")
def cost(db: Session = Depends(get_db)):
    """Real model usage by feature, for the writeup. Free tiers: ₹0, but tokens show headroom."""
    rows = db.execute(select(LlmLog.task, LlmLog.model, LlmLog.cached, func.count(), func.sum(LlmLog.tokens_in),
                             func.sum(LlmLog.tokens_out)).group_by(LlmLog.task, LlmLog.model, LlmLog.cached)).all()
    return [{"task": t, "model": m, "cached": bool(c), "calls": n, "tokens_in": ti or 0, "tokens_out": to or 0}
            for t, m, c, n, ti, to in rows]
