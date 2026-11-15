from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from finn.db import session_scope
from finn.main import app
from finn.models import Filing


def test_api_smoke():
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"]
        with session_scope() as s:
            s.add(Filing(id="nse:1:INFY", ticker="INFY", company="Infosys Limited", subject="Financial Result Updates",
                         filed_at=datetime.utcnow() - timedelta(hours=1), category="results", score=0.9, tier="S",
                         headline="Infosys: PAT +12% YoY", factors={"why": ["Results", "your holding"]}))
        feed = c.get("/feed?window=24h").json()
        assert feed["S"][0]["id"] == "nse:1:INFY"
        assert c.get("/filing/nse:1:INFY").json()["headline"].startswith("Infosys")
        assert c.post("/filing/nse:1:INFY/pin").json()["pinned"] is True

        rules = c.get("/rules").json()
        assert {r["source"] for r in rules} == {"default"} and len(rules) == 2
        parsed = c.post("/rules/parse", json={"text": "Alert me if Titan volume doubles"}).json()
        assert parsed["spec"]["type"] == "volume" and parsed["spec"]["scope"] == "TITAN"
        r = c.post("/rules", json={"spec": parsed["spec"], "source": "voice"}).json()
        assert r["label"] == "TITAN volume above 2× its 20-day average"
        assert c.post("/rules", json={"spec": {"type": "price"}}).status_code == 400

        a = c.post("/assistant", json={"text": "Open Infosys", "ctx": {}}).json()
        assert a == {"intent": "go", "route": "/company/INFY", "say": "Opening INFY."}
        a = c.post("/assistant", json={"text": "Alert me if it falls 5%", "ctx": {"screen": "company", "ticker": "INFY"}}).json()
        assert a["intent"] == "command" and a["rule"]["spec"]["scope"] == "INFY"
        a = c.post("/assistant", json={"text": "What happened at Infosys?", "ctx": {}}).json()
        assert a["intent"] == "ask" and "Infosys" in a["answer"]

        assert c.get("/portfolio").json()["holdings"][0]["ticker"] == "HDFCBANK"
        assert c.put("/portfolio/prefs", json={"price_pct": 4}).json()["price_pct"] == 4
        assert any(r["label"] == "any holding moves more than 4% in a day" for r in c.get("/rules").json())
        assert c.post("/push/register", json={"token": "ExponentPushToken[x]"}).json()["ok"]
        assert c.get("/search?q=infy").json()[0]["ticker"] == "INFY"
