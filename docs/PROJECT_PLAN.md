# Project plan

The 12-week plan, team split and milestone checklist from the project guide,
mapped onto what is actually in this repository.

---

## Team responsibilities

### CSE Core
| Area | Where it lives |
|---|---|
| Frontend | `frontend/src/pages/`, `frontend/src/components/` |
| Backend APIs | `backend/app/routers/` |
| Authentication | `backend/app/security.py`, `backend/app/deps.py`, `routers/auth.py` |
| Database | `backend/app/models.py`, `database/schema.sql` |
| Deployment | `docs/SETUP.md` §8, `run.bat` / `run.sh` |

### CSE AI
| Area | Where it lives |
|---|---|
| Resume parser | `ai/resume_parser.py` |
| ATS score | `ai/ats.py`, `ai/skills_db.py` |
| LLM integration | `ai/llm.py` |
| Speech to text | `ai/stt.py` |
| Answer evaluation | `ai/evaluator.py` |
| Recommendation engine | `ai/recommender.py` |

The two halves meet at exactly one place: the backend imports `ai/` as a
library. `ai/` has no web-framework or database imports, so it can be developed
and tested without running the server, and the API can be developed without
understanding the rubric.

---

## 12-week plan

| Week | Guide milestone | Deliverable in this repo | Status |
|---|---|---|---|
| 1 | Planning | Architecture, schema, API contract, role taxonomy | ✅ `docs/ARCHITECTURE.md`, `ai/skills_db.py` |
| 2 | Authentication | Register/login, bcrypt, JWT, admin bootstrap, ownership scoping | ✅ `routers/auth.py`, 14 tests |
| 3 | Resume upload | PDF/DOCX/TXT upload, storage, extraction, parsed-text preview | ✅ `routers/resumes.py` |
| 4 | Resume parsing | Contact, sections, skills via alias table, experience in months | ✅ `ai/resume_parser.py`, 13 tests |
| 5 | ATS scoring | 5 weighted sub-scores, JD keyword match, explainable suggestions | ✅ `ai/ats.py`, 11 tests |
| 6 | Question generation | LLM path + curated bank, company mixes, coding problems | ✅ `ai/question_gen.py` |
| 7 | Voice interview | MediaRecorder + Web Speech API, TTS questions, server STT | ✅ `useRecorder.ts`, `ai/stt.py` |
| 8 | AI evaluation | 5-dimension rubric, per-category weights, interview summary | ✅ `ai/evaluator.py` |
| 9 | Dashboard | Stats, score trend, reports, roadmap, admin console | ✅ 10 pages |
| 10 | Testing | 92 tests, no network or key required | ✅ `tests/` |
| 11 | Deployment | One-command launcher, Postgres switch, deploy guide | ✅ `run.bat`, `docs/SETUP.md` |
| 12 | Final documentation | README + 4 docs + inline rationale | ✅ `docs/` |

---

## Milestone checklist

| Milestone | Owner | Status | Evidence |
|---|---|---|---|
| Authentication | Core | ✅ Done | `POST /register`, `POST /login`, JWT, `tests/test_api_auth.py` (14 tests) |
| Resume parser | AI | ✅ Done | `ai/resume_parser.py`, `tests/test_resume_parser.py` (13 tests) |
| ATS score | AI | ✅ Done | `ai/ats.py`, `tests/test_ats.py` (11 tests) |
| Frontend | Core | ✅ Done | 10 pages, React + TS + Tailwind, typechecks clean |
| Voice interview | AI | ✅ Done | `useRecorder.ts` + `ai/stt.py`, three-tier fallback |
| Deployment | Core | ⬜ Not deployed | Runs locally; hosting guide in `docs/SETUP.md` §8 |

The last row is deliberately not ticked. The project runs end to end locally
and the deployment path is written up, but nothing is hosted yet, and two
things must be fixed first: uploads need object storage instead of local disk,
and `SECRET_KEY` must be set to a real value.

---

## Module coverage

All ten modules from the guide are implemented and verified in the browser.

| # | Module | Route | Verified |
|---|---|---|---|
| 1 | Authentication | `/login`, `/register` | ✅ registered, signed in, admin gate rejects non-admins |
| 2 | Dashboard | `/dashboard` | ✅ ATS 95, interview avg 68, 6 answers, trend |
| 3 | Resume upload | `/resume` | ✅ uploaded, 31 skills detected |
| 4 | Resume analyzer | `/resume` | ✅ scored 95/100 with 5-part breakdown |
| 5 | Role/company selection | `/interview` | ✅ 10 roles, 5 company styles, mix preview |
| 6 | AI interview | `/interview/:id` | ✅ 6 questions answered and scored individually |
| 7 | Coding interview | `/interview/:id` | ✅ static review, never executed |
| 8 | Reports | `/report/:id` | ✅ per-answer rubric + model answer |
| 9 | Learning roadmap | `/roadmap` | ✅ 20h across 3 weeks from measured weaknesses |
| 10 | Admin dashboard | `/admin` | ✅ stats, engine health, user table |

---

## Test coverage

```bash
python -m pytest tests -q
```

92 tests, ~9 seconds, no network and no API key.

| File | Tests | Covers |
|---|---|---|
| `test_resume_parser.py` | 13 | contact, sections, skill aliases, C++ vs C, months not years, bad files |
| `test_ats.py` | 11 | determinism, weights sum to 100, JD redistribution, role sensitivity |
| `test_question_gen_and_evaluator.py` | 20 | mixes, seeding, whole-bullet quoting, rubric ordering, code checks |
| `test_recommender.py` | 9 | priority order, weekly budget, splitting large items, trimming |
| `test_llm_seam.py` | 13 | offline fallback, provider swap, JSON extraction, vendor failure |
| `test_api_auth.py` | 14 | registration, enumeration resistance, cross-user access, admin gate |
| `test_api_flow.py` | 12 | the full journey: upload → analyse → interview → report → roadmap |

Three of these were written after a bug the tests themselves caught:

- `complete_json` re-raised non-`LLMError` exceptions, which would have ended
  an interview on a vendor 429.
- `generate_coding_problems` returned fewer problems than requested for roles
  matching only one problem.
- Wrapped resume bullets were quoted back mid-sentence.

---

## Known limitations

Worth stating plainly rather than being asked about them.

1. **The evaluator is unvalidated.** The rubric is defensible in design, but
   nobody has measured its agreement with human interviewers. The right next
   step is ~100 human-scored answers and a correlation number.
2. **Submitted code is not executed.** Static review only — safe execution needs
   a real container sandbox (`docs/ARCHITECTURE.md` §7).
3. **Live transcription is Chrome/Edge only.** Other browsers fall back to
   server-side transcription, which works but is not live.
4. **Uploads are on local disk.** Fine locally, wrong for a hosted deploy.
5. **Skill detection is alias-based.** A skill written in a way the alias table
   does not know is missed. It is auditable and fixable in one file, which is
   the trade made for determinism.
6. **English only.** Multi-language interviews are listed as a future
   enhancement in the guide and are not attempted here.

---

## Future enhancements from the guide

| Idea | Notes on feasibility |
|---|---|
| Recruiter dashboard | Schema already supports it — `v_user_activity` in `schema.sql` is the start |
| Avatar interviewer | The TTS layer is already isolated in `useSpeech.ts` |
| LinkedIn analysis | Needs their API; scraping breaks and violates terms |
| GitHub analysis | Practical: the public API gives languages, commit cadence and project sizes |
| Mobile app | The API is already the only backend; a React Native client is additive |
| Multi-language support | Whisper handles the audio; the question bank and rubric would need translating |
