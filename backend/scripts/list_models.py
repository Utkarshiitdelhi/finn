"""Print the model ids your Gemini and Groq keys can call right now. Run: python scripts/list_models.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx

from finn import config

r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
              headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=20)
print("GEMINI", r.status_code)
if r.status_code == 200:
    for m in r.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            print("  ", m["name"].removeprefix("models/"))
else:
    print(r.text[:500])

r = httpx.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, timeout=20)
print("GROQ", r.status_code)
if r.status_code == 200:
    for m in sorted(x["id"] for x in r.json()["data"]):
        print("  ", m)
else:
    print(r.text[:500])
