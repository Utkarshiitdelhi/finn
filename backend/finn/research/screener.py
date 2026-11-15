"""screener.in company page: standardised financial tables, about text, and links to annual reports
and concall transcripts. One page fetch gives almost everything the Company screen needs."""
from __future__ import annotations

import io
import logging
import re
import time

import httpx
from bs4 import BeautifulSoup

from .. import config

log = logging.getLogger("finn.screener")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=45, follow_redirects=True)
    return _client


def num(s: str):
    s = (s or "").replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").strip()
    if s in ("", "-", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _table(section) -> dict:
    if section is None:
        return {"periods": [], "rows": {}}
    t = section.find("table", class_="data-table") or section.find("table")
    if t is None:
        return {"periods": [], "rows": {}}
    head = [th.get_text(" ", strip=True) for th in t.find("thead").find_all("th")][1:]
    rows = {}
    for tr in t.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        name = re.sub(r"\s*\+\s*$", "", tds[0].get_text(" ", strip=True).replace("\xa0", " ")).strip()
        if not name or name.lower().startswith("raw pdf"):
            continue
        rows[name] = [num(td.get_text(strip=True)) for td in tds[1:]]
    return {"periods": head, "rows": rows}


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    name = soup.find("h1")
    about = soup.select_one(".company-profile .about") or soup.select_one(".about")
    key_points = soup.select_one(".company-profile .commentary")
    ratios = {}
    for li in soup.select("#top-ratios li"):
        n, v = li.select_one(".name"), li.select_one(".number")
        if n and v:
            ratios[n.get_text(strip=True)] = num(v.get_text(strip=True))
    docs = {"annual_reports": [], "transcripts": []}
    for a in soup.select(".documents.annual-reports a"):
        label = a.get_text(" ", strip=True)
        m = re.search(r"(\d{4})", label)
        docs["annual_reports"].append({"period": f"FY{m.group(1)}" if m else label, "url": a.get("href")})
    for li in soup.select(".documents.concalls li"):
        when = li.find("div")
        for a in li.find_all("a"):
            if a.get_text(strip=True).lower() == "transcript" and a.get("href"):
                docs["transcripts"].append({"period": when.get_text(strip=True) if when else "", "url": a["href"]})
    return {
        "name": name.get_text(strip=True) if name else "",
        "about": about.get_text(" ", strip=True) if about else "",
        "key_points": key_points.get_text(" ", strip=True)[:1500] if key_points else "",
        "ratios": ratios,
        "quarters": _table(soup.find("section", id="quarters")),
        "profit_loss": _table(soup.find("section", id="profit-loss")),
        "balance_sheet": _table(soup.find("section", id="balance-sheet")),
        "cash_flow": _table(soup.find("section", id="cash-flow")),
        "docs": docs,
    }


_page_cache: dict[str, dict] = {}


def company(ticker: str) -> dict:
    """Consolidated page if it has data, else standalone. Cached on disk for the day."""
    ticker = ticker.upper()
    if ticker in _page_cache:
        return _page_cache[ticker]
    cache = config.CACHE_DIR / "screener" / f"{ticker}-{time.strftime('%Y%m%d')}.html"
    html = cache.read_text() if cache.exists() else ""
    if not html:
        for url in (f"https://www.screener.in/company/{ticker}/consolidated/", f"https://www.screener.in/company/{ticker}/"):
            r = client().get(url)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            if parse(r.text)["quarters"]["periods"]:
                html = r.text
                break
            html = html or r.text
            time.sleep(1)
        if not html:
            raise LookupError(f"{ticker} not found on screener.in")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html)
    data = parse(html)
    data["ticker"] = ticker
    _page_cache[ticker] = data
    return data


def download_pdf(url: str) -> bytes:
    cache = config.CACHE_DIR / "pdf" / (re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".pdf")
    if cache.exists():
        return cache.read_bytes()
    r = client().get(url, headers={"Referer": "https://www.screener.in/"})
    r.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(r.content)
    return r.content


def pdf_pages(data: bytes, max_pages: int = 400) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    out = []
    for i, p in enumerate(reader.pages[:max_pages]):
        try:
            out.append(p.extract_text() or "")
        except Exception:
            out.append("")
    return out
