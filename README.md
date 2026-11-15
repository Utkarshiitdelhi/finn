# FINN: a phone-first investment agent

FINN shows an investor only what matters to **their** portfolio, then lets them dig into any of it in one tap. Push and pull are one loop. Every filing is ranked S/A/B/C by how material it is to you, every important item opens a cited research view, and every research view ends in something you can watch.

**Headline feature:** the promise tracker compares what management guided in the last 4–6 earnings calls with what they actually delivered.

Setup and external accounts are in **[SETUP.md](SETUP.md)**.

## Layout

```
backend/                FastAPI + batch jobs (Python)
  finn/classify.py      NSE subject → category (keyword rules; small model only for leftovers)
  finn/score.py         materiality = category weight × relevance × surprise × boost → S/A/B/C
  finn/enrich.py        results table (PDF → Gemini, arithmetic-checked; screener fallback), CFO/CEO bio, one-liners
  finn/pipeline.py      ingest → classify → score → enrich S/A → rescore; merges same-day price moves
  finn/rules.py         watch-rules engine + natural-language → rule (regex first, model second)
  finn/research/        screener.in parser, promise tracker, company cards, impact tree
  finn/assistant.py     FINN button: ask / command / go
  finn/llm.py           routing (Groq/Gemini small → mid → strong), cache by content hash, token log
  jobs/run.py           poll · eod · brief · research · load-snapshot
app/                    Expo (SDK 58) + Expo Router: Feed · Watch · Portfolio tabs, Company, Filing, Impact
.github/workflows/      scheduled batch jobs + keep-alive
render.yaml             backend deploy
```

## API

`GET /feed?window=24h|3d|7d` · `GET /filing/{id}` · `GET /alerts` · `GET/POST/PATCH/DELETE /rules` · `POST /rules/parse` ·
`GET /company/{ticker}` (builds on first call and returns progress) · `GET /impact/{series}` · `GET /search?q=` ·
`GET /portfolio` · `PUT /portfolio/prefs` · `POST /assistant` · `POST /assistant/voice` · `POST /push/register` · `GET /stats/cost`

## Cost

The runtime target is ₹0. Rules come before models, and only S/A items get model work. Every model call is cached by sha256(task + prompt version + model + document), so nothing is processed twice. `GET /stats/cost` reports calls and tokens by feature for the writeup.

## Grounding

The pull side reads only exchange filings, annual reports and transcripts (via screener.in links). Every claim carries a source and page. Each extracted quote is string-matched against its document, and claims whose quote can't be found are dropped. When the sources don't answer a question, FINN says "Not in the sources."
