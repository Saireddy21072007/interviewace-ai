# Architecture

How InterviewAce AI is put together, and the reasoning behind each decision.
This is the document to read before a viva — every section answers a "why did
you do it that way?" question.

---

## 1. The shape

```
┌─────────────────────────────────────────────────────────────┐
│  frontend/  React + TypeScript + Tailwind (Vite, port 5173) │
│  10 pages · one API client · JWT in localStorage            │
└───────────────────────────┬─────────────────────────────────┘
                            │  HTTP + JSON (multipart for files)
┌───────────────────────────▼─────────────────────────────────┐
│  backend/   FastAPI (port 8000)                             │
│  routers → schemas (Pydantic) → models (SQLAlchemy)         │
│  auth · file storage · orchestration only. No AI logic.     │
└───────────┬───────────────────────────────┬─────────────────┘
            │                               │
┌───────────▼────────────┐   ┌──────────────▼──────────────────┐
│  ai/  pure Python      │   │  Database                       │
│  no web framework      │   │  SQLite (dev) / PostgreSQL      │
│  no database           │   │  7 tables                       │
└───────────┬────────────┘   └─────────────────────────────────┘
            │
    ┌───────┴────────┐
    │  llm.py        │ ── Anthropic / OpenAI / Gemini / offline
    │  stt.py        │ ── faster-whisper / Whisper API / browser
    └────────────────┘
```

Three layers, one rule each:

- **`ai/`** imports no web framework and no database. Data in, data out.
- **`backend/`** contains no AI logic. It authenticates, stores, and calls `ai/`.
- **`frontend/`** contains no scoring logic. It renders what the API returns.

That separation is what lets the CSE-AI half of the team work on scoring
without running a server, and the CSE-Core half work on the API without
understanding the rubric.

---

## 2. Why the AI layer is a library, not a service

`ai/` is importable, synchronous Python. It is not a microservice and does not
own a queue.

For this workload that is the right call. The slowest operation is a single
LLM call of a few seconds; there is no training, no GPU and no batch job.
A separate service would add a network hop, a deployment target and a failure
mode in exchange for nothing. If the evaluator ever needs to run a fine-tuned
model on a GPU, `ai/` is already isolated enough to be lifted out behind the
same function signatures.

---

## 3. Why one file owns each provider

`llm.py` is the only file in the repository that imports `anthropic`, `openai`
or `google.genai`. `stt.py` is the only file that touches audio transcription.
Everything else calls two methods:

```python
llm.complete(system, user) -> str          # raises LLMError
llm.complete_json(system, user, fallback)  # NEVER raises
```

Swapping to a self-hosted Llama means rewriting one file. The resume parser,
question generator and evaluator do not change, and neither do their tests —
`tests/test_llm_seam.py` proves this by substituting a fake provider and
checking the same code paths produce model-generated output.

### The offline guarantee

`complete_json` returns the caller's fallback on *any* failure: no key, a rate
limit, a bad gateway, unparseable JSON. Every caller supplies a real fallback
built from rules and templates.

The consequence is that the entire product — upload, score, interview, report,
roadmap — works on a laptop with no internet and no billing account. The model
makes the output better; it is never the difference between working and broken.
That is a demo-day requirement. A live demo that fails because a vendor is
rate-limiting is not a demo.

The header badge shows which engine is live at all times, so "it works offline"
never becomes "we did not notice it was offline".

---

## 4. Why the scores are rules, not model calls

Resume parsing and ATS scoring are deterministic. Question generation and
answer evaluation prefer the model. That split is deliberate.

| | Rules | Model |
|---|---|---|
| Same input, same output | yes | no |
| Explainable to the candidate | yes | not really |
| Cost per call | zero | real |
| Good at judging a spoken answer | no | yes |
| Good at set intersection | yes | wasteful |

A candidate who uploads the same resume twice must see the same ATS score. A
model re-reading the resume drifts by a few points each time and destroys trust
in the number. Matching a resume against a role is set intersection — solving
it with an LLM is both slower and less accurate.

Conversely, judging whether a spoken answer had *depth* is exactly what rules
are bad at, so that is where the model earns its keep.

**Detail worth defending:** parsing is regex-based, and that is a feature. A
real ATS is regex-based too. If our parser cannot read a resume, the recruiter's
software cannot either — so a low parseability score is signal, not a bug. The
UI has a "Preview parsed text" button for exactly this reason.

---

## 5. The ATS score

Five sub-scores, fixed weights, 100 points, all arithmetic:

```
Skill match       40   0.75 × must-have coverage + 0.25 × nice-to-have coverage
Job description   15   keyword overlap with the posting (60% overlap = full marks)
Parseability      15   sections, contact block, length, extraction warnings
Impact            15   action verbs, quantified results, bullets, weak phrasing
Fit               15   experience years vs level, education, certifications
```

Design notes:

- **Must-have and nice-to-have are weighted separately.** Must-haves get you
  past the filter; nice-to-haves get you to the top of the pile. Without the
  split, a candidate who knows six trendy extras but no SQL would score well
  for a backend role — which is not what a real screen does.
- **No job description means its 15 points move to skill match.** A candidate is
  never penalised for something they did not provide.
- **60% keyword overlap scores full marks.** No honest resume mirrors an entire
  job posting, and rewarding 100% overlap would be rewarding keyword stuffing.
- **Experience is counted in months.** A summer internship is 0.2 years of real
  experience; rounding it to zero would under-score every student this product
  is built for.

---

## 6. The evaluation rubric

Five dimensions, 0-10 each, weighted by question category:

| | relevance | depth | structure | specificity | clarity |
|---|---|---|---|---|---|
| technical | 0.25 | **0.35** | 0.10 | 0.20 | 0.10 |
| behavioral | 0.20 | 0.15 | **0.30** | 0.20 | 0.15 |
| situational | 0.25 | 0.20 | 0.25 | 0.15 | 0.15 |
| resume | 0.20 | **0.30** | 0.15 | 0.25 | 0.10 |
| coding | 0.20 | **0.40** | 0.15 | 0.15 | 0.10 |

A behavioural answer with no structure fails no matter how technically deep it
is; a technical answer scores on depth. One flat weighting would hide both.

The heuristic scorer reads coverage of the question's expected points, answer
length, technical vocabulary, STAR markers, quantified claims, filler-word rate
and speaking pace. It is coarser than the model but directionally right, and it
never returns a null score.

**Detail worth defending:** the "did they quantify it" detector matches spelled
numbers as well as digits. A resume writes "480ms"; a candidate *says* "four
hundred and eighty milliseconds" or "from two days to about four hours". Only
matching digits would punish people for talking like humans.

---

## 7. Submitted code is never executed

The coding round reviews code statically: it parses it, checks for a named
function, an unreplaced stub, edge-case handling and obvious `O(n²)` scans, and
optionally asks the model to trace the logic.

Running candidate code safely needs a container, seccomp, resource limits and a
network namespace. That is a project in itself, and the alternative — `exec()`
on user input — is remote code execution on the server. Being honest about the
limit (the UI says so) is better than shipping a vulnerability. If we needed
real execution, the answer is a per-submission container with no network, a
CPU-second cap and a memory cap, not a sandbox implemented in Python.

---

## 8. The roadmap is a packing problem

The output is not a list of topics, it is a schedule that fits.

1. Rank gaps: missing must-have skills (critical) → measured interview
   weaknesses (high/medium) → missing nice-to-have skills (medium).
2. Flatten each gap into schedulable resources with realistic hour estimates.
3. First-fit pack into weeks against the candidate's stated weekly budget.
4. Split anything larger than one week across consecutive weeks.
5. Trim trailing empty weeks.

Interview weaknesses rank *above* nice-to-have skills because a candidate who
has every skill but cannot structure an answer fails at the same rate as one
who is missing Docker — and this product is the only thing that can see that.

Steps 4 and 5 both exist because of honesty: dropping the most important item
for being large is the wrong behaviour, and promising 8 weeks while filling 3
makes the plan look padded. The weekly heading is derived from what is actually
scheduled underneath it, for the same reason.

---

## 9. Data model

```
users ─┬─< resumes ──< interviews ──< questions ──< answers
       │                    │
       │                    └──── reports (1:1)
       └─< roadmaps
```

- **Analysis output is JSON, not columns.** `parsed`, `ats_result`, `scores`,
  `evaluation`, `weeks` are shapes owned by `ai/` that change whenever the model
  improves. A migration per tweak would couple AI iteration speed to the
  database. Anything we *query or sort by* — `ats_score`, `overall_score` — is a
  real column.
- **Scores are duplicated** between the JSON blob and their own column on
  purpose: the column is the query surface, the blob is the audit trail.
- **One answer per question**, enforced by a UNIQUE constraint. Re-answering
  overwrites. A second row would silently double-count in the report average.
- **Deletes cascade from the user down.** A product that records people speaking
  has to be able to forget them completely; `DELETE /me` removes every
  transcript and audio reference.
- **`resume_id` is `SET NULL`, not cascade.** Deleting a resume must not erase
  the interview history built on it.
- **Foreign keys are enabled on SQLite** with a `PRAGMA` on connect. Without it
  SQLite ignores them and quietly diverges from PostgreSQL — the class of bug
  that only appears after deployment.

---

## 10. Security

| Concern | How it is handled |
|---|---|
| Password storage | sha256 pre-hash → bcrypt (cost 12). The pre-hash exists because bcrypt silently truncates past 72 bytes. |
| Sessions | JWT, HS256, 24h expiry, issuer checked. |
| Account enumeration | Wrong password and unknown email return the identical 401. |
| Privilege escalation | Admin is granted only to `ADMIN_EMAIL` at registration. No promote endpoint exists. |
| Horizontal access | Every query is scoped by `user_id`. Guessing a resume ID returns 404, not someone else's resume. |
| Path traversal | Uploads are stored under a generated UUID name; the user's filename is only ever displayed. |
| Upload abuse | Extension allow-list and a size cap enforced before parsing. |
| Untrusted code | Never executed (section 7). |
| Admin overreach | Admins see counts and scores, never resume text, transcripts or audio. |
| Insecure defaults | A placeholder `SECRET_KEY` produces a startup warning and a banner in the admin console. |

`passlib` is deliberately not used — it is unmaintained and its bcrypt backend
breaks against bcrypt 4.x. Two functions do not justify a dependency that logs
errors on import.

---

## 11. Frontend notes

- **One API client.** Auth headers, JSON parsing and error handling are written
  once. A 401 clears the token and redirects, so an expired session can never
  leave the UI spinning forever.
- **Errors are shown verbatim.** The API is written so `detail` is always a
  sentence a candidate can act on, which means components never translate error
  codes into copy.
- **The mark scheme is hidden during the interview.** `QuestionOut` omits
  `expected_points`; the report includes it. Handing the candidate the answer
  key mid-question would make every score meaningless.
- **`/dashboard` is one endpoint, not six.** Otherwise the page fires six
  requests on load and renders in six stages.
- **The trend chart is hand-rolled SVG.** A charting library is ~90 KB for one
  graph on one page.
- **Roadmap progress is stored server-side.** A study plan that vanishes when
  the browser cache is cleared is a study plan people stop trusting.

---

## 12. What I would do next

1. **Move uploads off local disk** (S3/R2) — required before any real deploy.
2. **Evaluate the evaluator.** Build a labelled set of ~100 answers scored by
   humans and measure agreement. Right now the rubric is defensible in design
   but unvalidated in practice, and that is the honest weak point of the project.
3. **Stream the interview.** Today each answer is a round trip; a WebSocket
   with streaming STT would remove the pause between answering and hearing the
   next question.
4. **Re-transcription job.** The audio is already kept for it — one background
   task to upgrade old interviews when a better model is installed.
5. **Rate limiting** on `/register` and `/login`.
