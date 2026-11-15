"""Ingest filings (NSE, BSE fallback) and prices (yfinance).

NSE blocks most cloud IPs, so run `python -m jobs.ingest` from your laptop; each run also writes a
JSON snapshot to data/snapshots/ that is committed to the repo, so the demo never depends on a
live scrape.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta

import httpx

from . import config

log = logging.getLogger("finn.ingest")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
NSE_HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
               "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}


class NSE:
    """NSE needs a cookie warm-up request before its JSON API answers."""

    def __init__(self) -> None:
        self.client = httpx.Client(headers=NSE_HEADERS, timeout=30, follow_redirects=True, http2=False)
        self._warm = False

    def warm(self) -> None:
        if not self._warm:
            self.client.get("https://www.nseindia.com/")
            self.client.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements")
            self._warm = True

    def get_json(self, url: str, params: dict) -> list | dict:
        self.warm()
        for attempt in range(3):
            r = self.client.get(url, params=params)
            if r.status_code == 200 and r.text.strip().startswith(("[", "{")):
                return r.json()
            self._warm = False
            time.sleep(1.5 * (attempt + 1))
            self.warm()
        raise RuntimeError(f"NSE {url} failed: {r.status_code}")

    def announcements(self, start: date, end: date, symbol: str | None = None) -> list[dict]:
        params = {"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")}
        if symbol:
            params["symbol"] = symbol
        data = self.get_json("https://www.nseindia.com/api/corporate-announcements", params)
        return data if isinstance(data, list) else data.get("data", [])

    def download(self, url: str) -> bytes:
        self.warm()
        r = self.client.get(url)
        r.raise_for_status()
        return r.content


def parse_nse_time(s: str) -> datetime:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return datetime.utcnow()


def normalise_nse(row: dict) -> dict:
    """NSE announcement row -> our filing dict."""
    return {
        "id": f"nse:{row.get('seq_id') or row.get('an_dt')}:{row.get('symbol')}",
        "ticker": (row.get("symbol") or "").upper(),
        "company": row.get("sm_name") or "",
        "subject": row.get("desc") or "",
        "text": row.get("attchText") or "",
        "attachment_url": row.get("attchFile") or "",
        "filed_at": parse_nse_time(row.get("an_dt") or row.get("sort_date") or "").isoformat(),
        "industry": row.get("smIndustry") or "",
    }


def fetch_filings(tickers: list[str], days: int = 7) -> list[dict]:
    """All announcements in the window, kept for portfolio tickers and everything else
    (sector peers are scored later). Falls back to per-symbol calls if the bulk call fails."""
    end, start = date.today(), date.today() - timedelta(days=days)
    nse = NSE()
    rows: list[dict] = []
    try:
        rows = nse.announcements(start, end)
        log.info("NSE bulk: %d rows", len(rows))
    except Exception as e:
        log.warning("NSE bulk failed (%s); trying per symbol", e)
        for t in tickers:
            try:
                rows += nse.announcements(start, end, t)
                time.sleep(0.6)
            except Exception as e2:
                log.warning("NSE %s failed: %s", t, e2)
    if not rows:
        log.warning("NSE gave nothing; trying BSE")
        return fetch_bse(days)
    return [normalise_nse(r) for r in rows]


def fetch_bse(days: int = 7) -> list[dict]:
    """BSE announcements API fallback. BSE keys filings by scrip code, not NSE symbol, so this only
    fills gaps; the scrip->symbol map comes from data/bse_map.json if present."""
    path = config.BACKEND_DIR / "data" / "bse_map.json"
    scrip_to_sym = json.loads(path.read_text()) if path.exists() else {}
    end, start = date.today(), date.today() - timedelta(days=days)
    out = []
    with httpx.Client(headers={"User-Agent": UA, "Referer": "https://www.bseindia.com/"}, timeout=30) as c:
        for page in range(1, 6):
            r = c.get("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w", params={
                "pageno": page, "strCat": "-1", "strPrevDate": start.strftime("%Y%m%d"),
                "strScrip": "", "strSearch": "P", "strToDate": end.strftime("%Y%m%d"), "strType": "C", "subcategory": "-1"})
            if r.status_code != 200:
                break
            table = r.json().get("Table", [])
            if not table:
                break
            for row in table:
                sym = scrip_to_sym.get(str(row.get("SCRIP_CD")), "")
                if not sym:
                    continue
                att = row.get("ATTACHMENTNAME") or ""
                out.append({
                    "id": f"bse:{row.get('NEWSID')}", "ticker": sym, "company": row.get("SLONGNAME", ""),
                    "subject": row.get("NEWSSUB") or row.get("HEADLINE") or "", "text": row.get("HEADLINE") or "",
                    "attachment_url": f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att}" if att else "",
                    "filed_at": (row.get("NEWS_DT") or datetime.utcnow().isoformat())[:19], "industry": ""})
    return out


def save_snapshot(name: str, data) -> None:
    config.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (config.SNAPSHOT_DIR / name).write_text(json.dumps(data, indent=1, default=str))


def load_snapshot(name: str):
    p = config.SNAPSHOT_DIR / name
    return json.loads(p.read_text()) if p.exists() else None


# ---------------- prices ----------------
MACRO = {"CL=F": "Crude oil", "USDINR=X": "USD/INR", "GC=F": "Gold", "^NSEI": "Nifty 50"}


def fetch_prices(symbols: list[str], days: int = 60) -> list[dict]:
    """Daily close + volume via yfinance. NSE tickers get the .NS suffix; macro series pass through."""
    import yfinance as yf

    yf_syms = {s: (s if s in MACRO or s.startswith("^") or "=" in s else f"{s}.NS") for s in symbols}
    df = yf.download(list(yf_syms.values()), period=f"{days}d", interval="1d", group_by="ticker",
                     auto_adjust=False, progress=False, threads=True)
    rows = []
    for sym, ysym in yf_syms.items():
        try:
            sub = df[ysym] if len(yf_syms) > 1 else df
        except KeyError:
            log.warning("no price data for %s", ysym)
            continue
        for idx, r in sub.dropna(subset=["Close"]).iterrows():
            rows.append({"symbol": sym, "day": idx.date().isoformat(), "close": float(r["Close"]),
                         "volume": float(r.get("Volume", 0) or 0)})
    return rows
