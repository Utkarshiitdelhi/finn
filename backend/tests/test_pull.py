from conftest import FIX
from finn.research import periods, promise, screener
from finn.research.view import balance_card, cash_card, numbers_card

SC = screener.parse((FIX / "screener_sample.html").read_text())


def test_screener_parse():
    assert SC["name"] == "Sample Tech Ltd"
    assert SC["ratios"]["Market Cap"] == 640000
    assert SC["quarters"]["periods"][-1] == "Sep 2026"
    assert SC["quarters"]["rows"]["Sales"] == [1000, 1030, 1050, 1080, 1120]
    assert SC["quarters"]["rows"]["OPM %"][0] == 24
    assert "Raw PDF" not in SC["quarters"]["rows"]
    assert SC["docs"]["transcripts"][0] == {"period": "Oct 2026", "url": "https://example.com/t-oct26.pdf"}
    assert SC["docs"]["annual_reports"][0]["period"] == "FY2026"


def test_periods():
    assert periods.label_to_fq("Sep 2026") == (27, 2)
    assert periods.label_to_fq("Mar 2027") == (27, 4)
    assert periods.label_to_fq("Dec 2026") == (27, 3)
    assert periods.fq_to_label(27, 2) == "Sep 2026"
    assert periods.call_to_results_quarter("Oct 2026") == (27, 2)
    assert periods.call_to_results_quarter("Jan 2027") == (27, 3)
    assert periods.parse_period("Q2 FY27")["quarters"] == [(27, 2)]
    assert periods.parse_period("FY2027")["kind"] == "FY"


def test_actuals_and_verdicts():
    q = SC["quarters"]
    a = promise.actual_for("revenue_growth_yoy", "Q2FY27", q)
    assert a["status"] == "ok" and a["value"] == 12.0  # 1120 vs 1000
    assert promise.actual_for("revenue_growth_yoy", "FY27", q)["status"] == "pending"
    assert promise.actual_for("ebitda_margin", "Q2FY27", q)["value"] == round(285 / 1120 * 100, 1)
    claim = {"target_low": 12, "target_high": 14, "comparator": "range"}
    assert promise.number_verdict(claim, a)[0] == "Delivered"
    assert promise.number_verdict({"target_low": 15, "comparator": "at_least"}, a)[0] == "Missed"
    assert promise.number_verdict({"target_low": 13, "comparator": "about"}, a)[0] == "Partly"


def test_quote_check():
    pages = ["Good evening everyone.", "We expect revenue growth of 12 to 14% in constant currency for the year, driven by large deals."]
    assert promise.quote_found("We expect revenue growth of 12 to 14% in constant currency for the year", pages) == (True, 2)
    assert promise.quote_found("We expect margins to expand by 300 basis points next year for sure", pages)[0] is False


def test_link_and_judge_revisions():
    claims = [
        {"call": "Jul 2026", "metric": "revenue_growth_yoy", "period": "Q2FY27", "kind": "number", "target_low": 15, "target_high": 15,
         "comparator": "about", "target_text": "15%", "quote": "q1", "page": 3},
        {"call": "Oct 2026", "metric": "revenue_growth_yoy", "period": "Q2FY27", "kind": "number", "target_low": 12, "target_high": 13,
         "comparator": "range", "target_text": "12–13%", "quote": "q2", "page": 4},
        {"call": "Oct 2026", "metric": "ebitda_margin", "period": "FY27", "kind": "number", "target_low": 26, "target_high": 27,
         "comparator": "range", "target_text": "26–27%", "quote": "q3", "page": 5},
        {"call": "Jul 2026", "metric": "ebitda_margin", "period": "Q2FY27", "kind": "direction", "direction": "up",
         "target_text": "margins will improve", "quote": "q4", "page": 6},
    ]
    out = promise.link_and_judge(claims, SC["quarters"], use_model=False)
    by = {r["key"]: r for r in out["rows"]}
    rev = by["revenue_growth_yoy|Q2FY27"]
    assert rev["revised"] and [h["said"] for h in rev["history"]] == ["15%", "12–13%"] and rev["verdict"] == "Delivered"
    assert by["ebitda_margin|FY27"]["verdict"] == "Pending"
    # Q1FY27 margin 25.0% -> Q2FY27 25.4%
    assert by["ebitda_margin|Q2FY27"]["verdict"] == "Delivered"
    assert out["scorecard"]["text"] == "2 of 2 promises delivered"


def test_company_cards():
    n = numbers_card(SC)
    assert [y["period"] for y in n["years"]] == ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    assert n["cagr"]["revenue_3y"] == round(((4110 / 3200) ** (1 / 3) - 1) * 100, 1)
    c = cash_card(SC)
    assert c["cfo_to_pat_5y"] == round((620 + 610 + 720) / (600 + 650 + 700), 2)
    b = balance_card(SC)
    assert b["years"][-1] == {"period": "Mar 2026", "debt": 150, "equity": 2620, "de": round(150 / 2620, 2)}
