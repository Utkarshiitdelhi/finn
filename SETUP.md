# FINN setup: what you need to get, and the order to do it

Everything below is free. Expect about 45 minutes, most of it waiting on the first APK build.

## 1. Accounts and keys (get these first)

| # | What | Where | What you bring back |
|---|------|-------|---------------------|
| 1 | Gemini API key | aistudio.google.com → Get API key | `GEMINI_API_KEY` |
| 2 | Groq API key | console.groq.com → API Keys | `GROQ_API_KEY` |
| 3 | Supabase project | supabase.com → New project, region **Mumbai (ap-south-1)**, save the DB password | Connect → **Session pooler** URI → `DATABASE_URL` |
| 4 | Expo account | expo.dev → sign up | log in with `npx eas-cli@latest login` |
| 5 | Firebase project (for Android push) | console.firebase.google.com → Add project → Add app → Android, package name **`com.utkarsh.finn`** | `google-services.json` → put it in `app/` |
| 6 | FCM V1 service-account key | Firebase → Project settings → Service accounts → Generate new private key | a JSON file; upload it to EAS (step 4 below). **Don't commit it.** |
| 7 | GitHub repo | github.com/new, e.g. `finn` (public is fine, `.env` and keys are git-ignored) | repo URL |
| 8 | Render account | render.com → sign in with GitHub | — |

When you create the keys, check the current model names on each provider's model list. If they differ from the defaults in `backend/.env.example`, override them there.

## 2. On your Mac

Check: `python3 --version` (needs 3.11+), `node --version` (needs 20+), `git --version`. You also need an Android phone with "Install unknown apps" allowed for your browser or Files app.

```bash
cd ~/finn/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste DATABASE_URL, GEMINI_API_KEY, GROQ_API_KEY
python -m pytest              # 14 tests, no network needed

python -m jobs.run poll       # NSE filings (must run from your laptop: NSE blocks cloud IPs), score, enrich
python -m jobs.run eod        # prices + macro via yfinance, merge moves, price/volume rules
python -m jobs.run research INFY HDFCBANK   # promise tracker etc. (~1 min each, first time)
uvicorn finn.main:app --reload --host 0.0.0.0 --port 8000
```

`poll` writes `data/snapshots/filings-latest.json`. Commit it so the demo never depends on a live scrape (`python -m jobs.run load-snapshot` rebuilds from it).

## 3. App: run on your phone

```bash
cd ~/finn/app
npm install
cp .env.example .env          # EXPO_PUBLIC_API_URL=http://<your Mac's LAN IP>:8000  (ipconfig getifaddr en0)
npx expo start --web          # quick look in the browser
```

Push notifications, voice and the deep links need a real build, not Expo Go.

## 4. First APK (start this early, because the build queue can take 10–30 min)

```bash
cd ~/finn/app
npx eas-cli@latest init                     # writes your projectId into app.json
npx eas-cli@latest credentials              # Android → preview → Google Service Account → FCM V1 → upload the JSON from step 1.6
# set EXPO_PUBLIC_API_URL in eas.json → build.preview.env to your Render URL (after step 5)
npx eas-cli@latest build -p android --profile preview
```

Install the APK from the link EAS prints, open the app, and allow notifications. Then test a push:
`curl -X POST $API/push/test`.

## 5. Deploy the backend

1. Push the repo to GitHub.
2. Render → New → **Blueprint** → pick the repo. It reads `render.yaml`. Set `DATABASE_URL`, `GEMINI_API_KEY` and `GROQ_API_KEY`.
3. The URL will be something like `https://finn-api.onrender.com`. Put it in `app/eas.json`, rebuild the APK, and run `npx expo export -p web` for the web link (Render static site or Netlify drop).
4. In GitHub → Settings → Secrets → Actions, add `DATABASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `API_URL` (your Render URL). `.github/workflows/batch.yml` then runs polls, EOD, briefs and a keep-alive ping.

## 6. Decisions still open (from the design doc)

- **16th holding:** a mid-cap with recent pledging or a credit-rating action. Add it to `backend/data/portfolio.json`.
- **Research set:** 2–3 companies outside the portfolio that have 4 or more transcripts with clear numeric guidance. Run `python -m jobs.run research <TICKERS>`.
- Tune the tier thresholds in `finn/config.py` once a real week of filings is in.
