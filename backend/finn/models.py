"""Tables from the design doc: holdings, prices, filings (+ enrichment inline), rules, rule_hits,
documents, guidance_claims, exposures, push_tokens, llm_cache, llm_log, research, jobs, events."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Holding(Base):
    __tablename__ = "holdings"
    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    sector: Mapped[str] = mapped_column(String(80), default="")
    weight: Mapped[float] = mapped_column(Float, default=0.0)  # fraction of portfolio, 0..1
    starred: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    """Key/value user settings: starred categories, default thresholds."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("symbol", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)  # NSE ticker or macro series (CL=F)
    day: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0)


class Filing(Base):
    __tablename__ = "filings"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # "nse:<seq_id>"
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    attachment_url: Mapped[str] = mapped_column(String(500), default="")
    filed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    category: Mapped[str] = mapped_column(String(40), default="unclassified")
    subtype: Mapped[str] = mapped_column(String(40), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[str] = mapped_column(String(1), default="C", index=True)
    factors: Mapped[dict] = mapped_column(JSON, default=dict)
    headline: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    card: Mapped[dict] = mapped_column(JSON, default=dict)  # category-specific payload (results table, bio…)
    price_move: Mapped[dict] = mapped_column(JSON, default=dict)  # merged same-day EOD move
    enriched: Mapped[bool] = mapped_column(Boolean, default=False)
    pushed: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class Event(Base):
    """Scheduled corporate events (results board meetings) for event-date rules."""
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("ticker", "event", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    event: Mapped[str] = mapped_column(String(40))
    day: Mapped[date] = mapped_column(Date)
    source_filing: Mapped[str] = mapped_column(String(80), default="")


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spec: Mapped[dict] = mapped_column(JSON)
    label: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(20), default="form")  # form | voice | text | default
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RuleHit(Base):
    __tablename__ = "rule_hits"
    __table_args__ = (UniqueConstraint("rule_id", "key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(120))  # dedupe key, e.g. "TITAN:2026-11-14"
    message: Mapped[str] = mapped_column(String(400))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    hit_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    pushed: Mapped[bool] = mapped_column(Boolean, default=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # transcript | annual_report | results_pdf
    period: Mapped[str] = mapped_column(String(40), default="")  # "Oct 2026", "FY2026"
    url: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    pages: Mapped[list] = mapped_column(JSON, default=list)  # page texts


class GuidanceClaim(Base):
    __tablename__ = "guidance_claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    doc_id: Mapped[int] = mapped_column(Integer)
    call_period: Mapped[str] = mapped_column(String(40))
    metric: Mapped[str] = mapped_column(String(80))
    target_text: Mapped[str] = mapped_column(String(200))
    period: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(12))  # number | direction
    quote: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str] = mapped_column(String(120), default="")
    page: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # lo/hi/unit/link key/verdict/actual


class Exposure(Base):
    __tablename__ = "exposures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    factor: Mapped[str] = mapped_column(String(40), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # helps | hurts
    strength: Mapped[str] = mapped_column(String(8))  # high | medium | low
    quote: Mapped[str] = mapped_column(Text)
    page: Mapped[int] = mapped_column(Integer, default=0)
    doc_id: Mapped[int] = mapped_column(Integer, default=0)


class Research(Base):
    """Cached company research view (all cards) for one ticker."""
    __tablename__ = "research"
    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    view: Mapped[dict] = mapped_column(JSON, default=dict)
    built_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "research:INFY"
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | done | error
    steps: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PushToken(Base):
    __tablename__ = "push_tokens"
    token: Mapped[str] = mapped_column(String(200), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), default="android")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LlmCache(Base):
    __tablename__ = "llm_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    output: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LlmLog(Base):
    __tablename__ = "llm_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(80))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
