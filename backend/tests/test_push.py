from datetime import date, datetime, timedelta

from conftest import FIX
from finn import pipeline, rules
from finn.classify import classify
from finn.db import session_scope
from finn.feed import feed
from finn.models import Filing, Price, Rule
from finn.research import screener
from finn.score import Portfolio, score_filing


def test_classify_rules():
    cases = {
        ("Outcome of Board Meeting-Financial Results", ""): "results",
        ("Financial Result Updates", ""): "results",
        ("Change in Directors/ Key Managerial Personnel/ Auditor/ Compliance Officer/ Share Transfer Agent", "Resignation of Mr X as Chief Financial Officer"): "management_change",
        ("Credit Rating", "CRISIL has downgraded the long term rating"): "credit_rating",
        ("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of the earnings call"): "earnings_call",
        ("Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of meeting"): "investor_meetings",
        ("Trading Window-XBRL", ""): "routine",
        ("Copy of Newspaper Publication", ""): "routine",
        ("Board Meeting Intimation", "to consider financial results on 20-Nov-2026"): "board_meeting",
        ("Disclosure under SEBI Takeover Regulations", ""): "insider_trading",
        ("Bagging/Receiving of orders/contracts", "order worth Rs 2,000 crore"): "press_release",
        ("Dividend", ""): "dividend",
        ("Allotment of Securities", ""): "fund_raise",
    }
    for (subj, text), want in cases.items():
        assert classify(subj, text, use_model=False)[0] == want, subj


def test_subtypes():
    assert classify("Change in Management", "Mr A appointed as Chief Executive Officer")[1] == "top"
    assert classify("Change in Directors", "Appointment of Ms B as Independent Director")[1] == "independent"
    assert classify("Credit Rating", "ICRA has reaffirmed the rating")[1] == "reaffirm"


PF = Portfolio(holdings={"INFY": {"sector": "IT services", "weight": 0.09}, "HDFCBANK": {"sector": "Private bank", "weight": 0.1}})


def test_default_tiers():
    t = lambda tk, sec, cat, sub="": score_filing(tk, sec, cat, sub, {}, {}, PF)[1]  # noqa: E731
    assert t("INFY", "IT services", "results") == "S"
    assert t("WIPRO", "IT services", "results") == "B"  # sector peer
    assert t("XYZ", "", "results") == "C"  # outside portfolio
    assert t("INFY", "IT services", "management_change", "top") == "S"
    assert t("INFY", "IT services", "management_change", "independent") == "B"
    assert t("HDFCBANK", "Private bank", "credit_rating", "downgrade") == "S"
    assert t("HDFCBANK", "Private bank", "credit_rating", "reaffirm") == "B"
    assert t("INFY", "IT services", "pledging") == "A"
    assert t("INFY", "IT services", "dividend") == "B"
    assert t("INFY", "IT services", "routine") == "C"
    assert t("INFY", "IT services", "earnings_call") == "C"
    # pledge jump > 5pp escalates A -> S
    assert score_filing("INFY", "IT services", "pledging", "", {"pledge_change_pp": 7}, {}, PF)[1] == "S"


def _seed(s):
    pipeline.load_portfolio_file(s)
    now = datetime.utcnow()
    rows = [
        {"id": "nse:1:INFY", "ticker": "INFY", "company": "Infosys Limited", "subject": "Financial Result Updates", "text": "Results for Q2", "filed_at": (now - timedelta(hours=2)).isoformat()},
        {"id": "nse:2:TCS", "ticker": "TCS", "company": "Tata Consultancy Services Limited", "subject": "Change in Management", "text": "Resignation of Chief Financial Officer", "filed_at": (now - timedelta(hours=3)).isoformat()},
        {"id": "nse:3:TITAN", "ticker": "TITAN", "company": "Titan Company Limited", "subject": "Trading Window-XBRL", "text": "", "filed_at": (now - timedelta(hours=4)).isoformat()},
        {"id": "nse:4:WIPRO", "ticker": "WIPRO", "company": "Wipro Limited", "subject": "Financial Result Updates", "text": "", "filed_at": (now - timedelta(hours=5)).isoformat()},
        {"id": "nse:5:LT", "ticker": "LT", "company": "Larsen & Toubro Limited", "subject": "Copy of Newspaper Publication", "text": "", "filed_at": (now - timedelta(hours=6)).isoformat()},
        {"id": "nse:6:LT", "ticker": "LT", "company": "Larsen & Toubro Limited", "subject": "Board Meeting Intimation", "text": "to consider financial results on 20-Jan-2027", "filed_at": (now - timedelta(days=5)).isoformat()},
    ]
    return pipeline.upsert_filings(s, rows)


def test_pipeline_feed_and_results_fallback():
    sc = screener.parse((FIX / "screener_sample.html").read_text())
    with session_scope() as s:
        ids = _seed(s)
        stats = pipeline.process(s, ids, screener=lambda t: sc["quarters"], use_models=False)
        assert stats["S"] == 2
        f = s.get(Filing, "nse:1:INFY")
        assert f.card["rows"][0]["metric"] == "revenue" and f.card["revenue"]["q"] == 1120
        assert f.card["pat"]["yoy_pct"] == round((202 - 169) / 169 * 100, 1)
        assert "PAT" in f.headline
        out = feed(s, "24h")
    assert [c["id"] for c in out["S"]] == ["nse:1:INFY", "nse:2:TCS"]
    assert out["B"][0]["ticker"] == "WIPRO"
    assert out["C"]["count"] == 2 and out["C"]["by_category"] == {"Routine": 2}
    assert out["S"][0]["why"]  # "why S?" chip


def test_board_meeting_creates_event_and_event_rule_fires():
    with session_scope() as s:
        _seed(s)
        r = Rule(spec=rules.validate({"type": "event", "ticker": "LT", "offset_days": -2}), label="x")
        s.add(r)
        s.flush()
        hits = rules.evaluate_eod(s, date(2027, 1, 18))
        assert len(hits) == 1 and "LT results board meeting in 2 days" in hits[0].message


def _prices(s, sym, closes, vols):
    d0 = date(2026, 10, 1)
    for i, (c, v) in enumerate(zip(closes, vols)):
        s.add(Price(symbol=sym, day=d0 + timedelta(days=i), close=c, volume=v))


def test_eod_price_volume_rules_merge_and_dedupe():
    with session_scope() as s:
        pipeline.load_portfolio_file(s)
        rules.ensure_defaults(s)
        _prices(s, "TCS", [100] * 20 + [93.8], [1000] * 20 + [3100])
        day = date(2026, 10, 21)
        s.add(Filing(id="nse:9:TCS", ticker="TCS", company="Tata Consultancy Services Limited", subject="Change in Management",
                     text="Resignation of CFO", filed_at=datetime(2026, 10, 21, 11, 0), category="management_change", subtype="top",
                     headline="TCS: CFO resigns"))
        s.flush()
        pipeline.process(s, ["nse:9:TCS"], use_models=False)
        merged = pipeline.merge_price_alerts(s, day)
        assert merged and merged[0].price_move["pct"] == -6.2 and merged[0].price_move["vol_ratio"] == 3.1
        hits = rules.evaluate_eod(s, day)
        msgs = [h.message for h in hits]
        assert any("TCS -6.2% on 3.1× its 20-day volume, same day as: TCS: CFO resigns" in m for m in msgs)
        assert len(hits) == 2  # price rule + volume rule
        assert rules.evaluate_eod(s, day) == []  # deduped


def test_rule_parsing():
    with session_scope() as s:
        pipeline.load_portfolio_file(s)
        p = lambda t: rules.parse_rule_text(s, t)  # noqa: E731
        r = p("Tell me if Titan moves more than 4% in a day")
        assert r["spec"] == {"type": "price", "scope": "TITAN", "op": "abs_gt", "value": 4.0, "metric": "pct_change"}
        r = p("Alert me if Infosys falls 5%")
        assert r["spec"]["op"] == "lt" and r["spec"]["scope"] == "INFY"
        assert p("volume above 2x its 20-day average on my holdings")["spec"]["type"] == "volume"
        r = p("Any management change at my banks")
        assert r["spec"] == {"type": "filing", "scope": "sector:Private bank", "category": "management_change"}
        r = p("Remind me 2 days before Infosys results")
        assert r["spec"]["type"] == "event" and r["spec"]["offset_days"] == -2
        assert p("If crude rises 3% in a day")["spec"] == {"type": "macro", "series": "CL=F", "op": "gt", "value": 3.0, "metric": "pct_change"}
        assert p("Remind me when Infosys's concall transcript is out")["spec"]["category"] == "earnings_call"
        r = p("When Infosys posts results and the transcript is out")
        assert r["spec"]["type"] == "all_of"
        r = p("Tell me when sentiment on Titan turns negative")
        assert "error" in r and r["closest"]["scope"] == "TITAN"
