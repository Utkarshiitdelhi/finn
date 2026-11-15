"""Indian fiscal periods. FY27 = Apr 2026–Mar 2027. Q1 Apr–Jun, Q2 Jul–Sep, Q3 Oct–Dec, Q4 Jan–Mar.
screener labels quarters by their end month ("Sep 2026" = Q2FY27) and years by March ("Mar 2027" = FY27)."""
from __future__ import annotations

import re

_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_Q_END = {1: 6, 2: 9, 3: 12, 4: 3}


def label_to_fq(label: str) -> tuple[int, int] | None:
    """'Sep 2026' -> (27, 2)."""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", label.strip())
    if not m:
        return None
    mon, yr = _MONTHS[m.group(1).lower()], int(m.group(2))
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(mon)
    if q is None:
        return None
    fy = (yr + 1 if mon >= 4 else yr) % 100
    return fy, q


def fq_to_label(fy: int, q: int) -> str:
    mon = _Q_END[q]
    yr = 2000 + (fy - 1 if mon >= 4 else fy)
    return f"{['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][mon]} {yr}"


def call_to_results_quarter(call_label: str) -> tuple[int, int] | None:
    """A concall in 'Oct 2026' discusses the quarter that just ended (Q2FY27)."""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", call_label.strip())
    if not m:
        return None
    mon, yr = _MONTHS[m.group(1).lower()], int(m.group(2))
    # quarter that ended most recently before or in this month
    end_mon = {1: 12, 2: 12, 3: 12, 4: 3, 5: 3, 6: 3, 7: 6, 8: 6, 9: 6, 10: 9, 11: 9, 12: 9}[mon]
    end_yr = yr - 1 if mon <= 3 and end_mon == 12 else yr
    return label_to_fq(f"{['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][end_mon]} {end_yr}")


def parse_period(p: str) -> dict | None:
    """'Q3FY27' | 'H2FY27' | 'FY27' | 'FY2027' -> {"kind","fy","n","quarters":[(fy,q),...]}"""
    s = re.sub(r"[\s\-']", "", (p or "").upper())
    m = re.fullmatch(r"Q([1-4])FY(\d{2}|\d{4})", s)
    if m:
        fy = int(m.group(2)) % 100
        return {"kind": "Q", "fy": fy, "n": int(m.group(1)), "quarters": [(fy, int(m.group(1)))]}
    m = re.fullmatch(r"H([12])FY(\d{2}|\d{4})", s)
    if m:
        fy, h = int(m.group(2)) % 100, int(m.group(1))
        return {"kind": "H", "fy": fy, "n": h, "quarters": [(fy, 1), (fy, 2)] if h == 1 else [(fy, 3), (fy, 4)]}
    m = re.fullmatch(r"FY(\d{2}|\d{4})", s)
    if m:
        fy = int(m.group(1)) % 100
        return {"kind": "FY", "fy": fy, "n": 0, "quarters": [(fy, q) for q in (1, 2, 3, 4)]}
    return None


def prev_year(quarters: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(fy - 1, q) for fy, q in quarters]
