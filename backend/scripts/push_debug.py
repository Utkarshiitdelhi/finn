"""Send a test push to every registered token and print Expo's ticket AND delivery receipt.
The receipt holds the real FCM error (InvalidCredentials, MismatchSenderId, DeviceNotRegistered…).
Run: python scripts/push_debug.py"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from sqlalchemy import select

from finn.db import session_scope
from finn.models import PushToken

with session_scope() as s:
    tokens = [t.token for t in s.scalars(select(PushToken)).all()]
print("tokens:", tokens)
if not tokens:
    sys.exit("no registered tokens")
msgs = [{"to": t, "title": "FINN debug", "body": "If you see this, push works.", "sound": "default",
         "channelId": "default", "priority": "high", "data": {"url": "/"}} for t in tokens]
r = httpx.post("https://exp.host/--/api/v2/push/send", json=msgs, timeout=30)
print("send:", r.status_code, json.dumps(r.json(), indent=1))
ids = [d["id"] for d in r.json().get("data", []) if d.get("id")]
if not ids:
    sys.exit("no ticket ids (see errors above)")
print("waiting 8 s for delivery receipts…")
time.sleep(8)
rr = httpx.post("https://exp.host/--/api/v2/push/getReceipts", json={"ids": ids}, timeout=30)
print("receipts:", json.dumps(rr.json(), indent=1))
