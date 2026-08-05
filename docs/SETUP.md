# Setup

Everything below is optional. `run.bat` (Windows) or `./run.sh` (macOS/Linux)
already installs and starts the whole project with no configuration at all.
This document is for when you want to change something.

---

## 1. Requirements

| | Minimum | Notes |
|---|---|---|
| Python | 3.11 | 3.12 is what this was built and tested on |
| Node.js | 18 | only needed for the web app; the API runs without it |
| Git | any | |
| Disk | ~400 MB | mostly `node_modules` |

Check what you have:

```bash
python --version
```

```bash
node --version
```

---

## 2. Manual install

If you would rather not use the launcher:

```bash
python -m pip install -r backend/requirements.txt
```

```bash
npm install --prefix frontend
```

```bash
copy .env.example .env
```

(`cp .env.example .env` on macOS/Linux.)

Then run the two servers in **two separate terminals**:

```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```

```bash
npm run dev --prefix frontend
```

Run the API command from the repository root — `backend.app.main` is resolved
relative to it.

- Web app: http://localhost:5173
- API docs: http://localhost:8000/docs

---

## 3. Configuration

Every setting lives in `.env` and has a working default. The full list with
comments is in `.env.example`. The ones you are most likely to touch:

### Signing key

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Put the output in `SECRET_KEY`. Until you do, the admin console shows a warning
and the API logs one at startup — with a known key, anyone can forge a token.

Changing `SECRET_KEY` invalidates every existing session, so everyone has to
sign in again. That is the intended behaviour, not a bug.

### Admin account

```
ADMIN_EMAIL=you@example.com
```

The first account registered with that address becomes the admin. There is no
"promote to admin" endpoint on purpose — a privilege-escalation route is not
something a student project should ship.

---

## 4. PostgreSQL instead of SQLite

SQLite is the default so the project runs with zero setup. The models,
queries and API are identical on PostgreSQL; only the connection string changes.

```bash
createdb interviewace
```

```bash
psql -d interviewace -f database/schema.sql
```

Then in `.env`:

```
DATABASE_URL=postgresql+psycopg://interviewace:secret@localhost:5432/interviewace
```

`psycopg[binary]` is already in `requirements.txt`, so nothing else to install.

Optional demo data (two accounts, one scored interview — password `DemoPass123`):

```bash
psql -d interviewace -f database/seed.sql
```

You do not have to run `schema.sql`: the app creates its tables automatically on
startup. The file exists so the schema is reviewable as plain SQL, and it adds
JSONB, CHECK constraints and a GIN index on skills that the portable ORM types
cannot express.

---

## 5. Turning on a real language model

Without a key the app uses the offline question bank and heuristic scorer, and
says so in the header badge. To switch on a model, put **one** of these in
`.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```

Then install the matching SDK (they are commented out in
`backend/requirements.txt` so nobody is forced to install all three):

```bash
python -m pip install anthropic
```

`LLM_PROVIDER=auto` picks whichever key is present, preferring Anthropic, then
OpenAI, then Gemini. Force one with `LLM_PROVIDER=openai`, or force the offline
engine with `LLM_PROVIDER=offline`. Override the model with `LLM_MODEL`.

Restart the API and check:

```bash
curl http://localhost:8000/health
```

`llm.available` should be `true`.

### What changes when a model is on

Questions are written from your resume text instead of drawn from the bank, and
answers are graded by the model against the same five-dimension rubric. Resume
parsing and the ATS score do **not** change — those are rules by design, so the
score stays reproducible.

---

## 6. Better speech-to-text

Voice interviews work out of the box using the browser's Web Speech API
(Chrome and Edge only). For accurate transcription that works in any browser
and never leaves the machine:

```bash
python -m pip install faster-whisper
```

That is it — `STT_PROVIDER=auto` finds it. The first transcription downloads
the model (~150 MB for `base.en`) and takes about a minute; every one after
that is fast. Change the model with `WHISPER_MODEL` (`tiny.en`, `base.en`,
`small.en`).

Alternatively, with `OPENAI_API_KEY` set, `STT_PROVIDER=openai-whisper` uses
the hosted Whisper API.

Audio is stored either way, so an interview recorded today can be re-transcribed
with a better model tomorrow without asking the candidate to repeat it.

---

## 7. Troubleshooting

**"Cannot reach the server. Is the backend running on port 8000?"**
The API is not running, or it crashed. Check its terminal window.

**Port already in use**

```bash
run.bat stop
```

**`ModuleNotFoundError: No module named 'ai'`**
The API was started from the wrong directory. Run it from the repository root.

**Microphone permission denied**
Allow it via the icon in the address bar. Voice recording needs `localhost` or
HTTPS — browsers block `getUserMedia` on plain HTTP from any other host.

**Live transcription does nothing**
The Web Speech API only exists in Chrome and Edge. Everything still works: the
audio is uploaded and transcribed server-side, you just do not see words appear
while speaking. Install `faster-whisper` for the best result.

**A PDF uploads but scores near zero on parseability**
It is probably a scan. Click "Preview parsed text" — if that is empty, real ATS
software sees the same nothing. Export a text-based PDF.

**Everything says "Offline engine"**
That is correct with no API key. See section 5.

---

## 8. Deployment sketch

The project guide targets Vercel + Render/Railway.

**Backend (Render / Railway)**
- Build: `pip install -r backend/requirements.txt`
- Start: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
- Env: `SECRET_KEY`, `DATABASE_URL` (managed Postgres), `CORS_ORIGINS`
  (your frontend URL), `ADMIN_EMAIL`, and an LLM key if you want one.

**Frontend (Vercel)**
- Root directory: `frontend`
- Build: `npm run build`, output `dist`
- Env: `VITE_API_URL=https://your-api.onrender.com`

Two things to get right before it is really deployed:

1. **Uploads.** `storage/` is local disk. On Render's ephemeral filesystem it
   is wiped on redeploy — move resume files and audio to S3 or Cloudflare R2.
2. **CORS.** `CORS_ORIGINS` must list the exact frontend origin. A wildcard with
   credentials enabled is rejected by browsers anyway.
