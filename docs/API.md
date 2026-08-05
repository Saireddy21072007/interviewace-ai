# API reference

Base URL in development: `http://localhost:8000`
Interactive docs (try every endpoint in the browser): `http://localhost:8000/docs`

All endpoints except `/health`, `/roles`, `/companies`, `/register` and
`/login` require a bearer token:

```
Authorization: Bearer <access_token>
```

Errors always return `{"detail": "<a sentence you can show the user>"}`.

| Status | Meaning here |
|---|---|
| 400 | Malformed request (empty file, missing id) |
| 401 | Not signed in, or the token expired/was tampered with |
| 403 | Signed in but not allowed (admin route, disabled account) |
| 404 | Not found, **or** owned by another user — the two are indistinguishable on purpose |
| 409 | Conflict (email taken, roadmap requested before analysing a resume) |
| 413 | File too large |
| 415 | Unsupported file type |
| 422 | Validation failed |

---

## The nine endpoints from the project guide

These are implemented at exactly the paths the guide specifies.

| Method | Path |
|---|---|
| POST | `/register` |
| POST | `/login` |
| POST | `/upload-resume` |
| POST | `/analyze-resume` |
| POST | `/generate-questions` |
| POST | `/submit-answer` |
| POST | `/evaluate` |
| GET | `/report` |
| GET | `/roadmap` |

Everything else below is an addition the app needed.

---

## Auth

### POST /register → 201

```json
{
  "email": "ananya@example.com",
  "password": "GoodPass123",
  "full_name": "Ananya Sharma",
  "target_role": "full-stack-developer",
  "experience_level": "fresher"
}
```

Returns a token immediately — there is no "registered but not signed in" state.

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in_minutes": 1440,
  "user": { "id": 1, "email": "ananya@example.com", "role": "user", "...": "..." }
}
```

Password rules: 8+ characters, at least one letter and one number (422 otherwise).
Duplicate email returns 409.

### POST /login → 200

```json
{ "email": "ananya@example.com", "password": "GoodPass123" }
```

Same response shape. Wrong password and unknown email return an identical 401,
so the endpoint cannot be used to discover which emails are registered.

### Other auth routes

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | current user |
| PATCH | `/me` | `full_name`, `target_role`, `experience_level` |
| POST | `/me/password` | needs `current_password`; 204 on success |
| DELETE | `/me` | deletes the account and every resume, interview, transcript and report |

---

## Resumes

### POST /upload-resume → 201

`multipart/form-data`

| Field | Type | |
|---|---|---|
| `file` | file | PDF, DOCX or TXT, max 10 MB |
| `make_primary` | bool | default `true` |

```json
{
  "resume": { "id": 1, "filename": "ananya.pdf", "skills": ["React", "..."], "...": "..." },
  "detected_skills": ["Docker", "FastAPI", "Git", "React", "..."],
  "warnings": [],
  "message": "Read 255 words and detected 31 skills."
}
```

`warnings` is where a scanned PDF is reported. Upload never fails because of
bad content — an unreadable file is stored with a warning, because that is
itself the finding.

### POST /analyze-resume → 200

```json
{
  "resume_id": 1,
  "role_key": "full-stack-developer",
  "experience_level": "fresher",
  "job_description": "We are hiring a Full Stack Developer... Kubernetes required."
}
```

Every field is optional. Omit `resume_id` and it uses your primary resume;
omit `role_key` and it uses your profile's target role.

```json
{
  "resume_id": 1,
  "score": 95,
  "grade": "A+",
  "band": "Strong - likely to pass automated screening",
  "role_title": "Full Stack Developer",
  "breakdown": [
    {
      "name": "Skill match", "key": "skills", "score": 38.8, "max": 40,
      "detail": "6/6 required and 7/8 preferred skills found.",
      "missing_must_have": [], "suggestions": []
    }
  ],
  "matched_skills": ["Docker", "Git", "React", "..."],
  "missing_must_have": [],
  "missing_good_to_have": ["System Design"],
  "extra_skills": ["FastAPI", "Python", "..."],
  "suggestions": ["The posting repeatedly uses these words that your resume never does: ..."],
  "review": { "one_line": "95/100 for Full Stack Developer: ...", "strengths": ["..."] }
}
```

`breakdown[].max` always sums to 100. Without a job description that sub-score
is absent and its 15 points are added to skill match.

### Other resume routes

| Method | Path | Notes |
|---|---|---|
| GET | `/resumes` | list (no raw text — it is large) |
| GET | `/resumes/{id}` | full detail |
| GET | `/resumes/{id}/text` | the extracted text, so the UI can show what the parser saw |
| DELETE | `/resumes/{id}` | 204 |

---

## Interviews

### POST /generate-questions → 201

```json
{
  "resume_id": 1,
  "role_key": "full-stack-developer",
  "company_key": "product-startup",
  "mode": "voice",
  "difficulty": "medium",
  "count": 6,
  "coding_problems": 1
}
```

```json
{
  "interview": { "id": 1, "status": "in_progress", "...": "..." },
  "questions": [
    {
      "id": 1, "index": 1, "category": "behavioral", "skill": null,
      "difficulty": "easy", "text": "Tell me about a time you received hard feedback.",
      "time_limit_sec": 120, "source": "bank", "problem": {}
    }
  ],
  "engine": "bank"
}
```

`engine` is `"llm"` or `"bank"` — the UI shows it so a demo is honest about
which engine produced the questions.

`expected_points` is deliberately **not** returned here. It appears in
`/report` after the interview.

Question generation is seeded by interview id, so reloading the page returns
the same interview rather than a new set of questions.

### POST /submit-answer → 200

Typed answers and code submissions.

```json
{
  "question_id": 1,
  "transcript": "At the time I was three weeks into my internship...",
  "duration_sec": 58,
  "code": "",
  "language": "python",
  "evaluate_now": true
}
```

```json
{
  "answer": { "id": 1, "overall_score": 68, "scores": { "relevance": 7.3, "...": 0 },
              "evaluation": { "strengths": ["..."], "improvements": ["..."] } },
  "next_question": { "id": 2, "index": 2, "...": "..." },
  "answered": 1,
  "total": 6
}
```

`evaluate_now: false` banks the answer without scoring it — useful on a slow
connection. `POST /evaluate` scores everything at the end.

Re-submitting the same `question_id` overwrites; it never creates a second row.

### POST /submit-answer/audio → 200

`multipart/form-data`

| Field | Type | |
|---|---|---|
| `question_id` | int | |
| `audio` | file | webm / ogg / wav / mp3 / m4a |
| `browser_transcript` | string | what the Web Speech API heard, if anything |
| `duration_sec` | float | the browser knows this precisely |
| `evaluate_now` | bool | default `true` |

The server transcribes with faster-whisper or the Whisper API when available and
falls back to `browser_transcript` otherwise. The response adds:

```json
{ "transcription": { "text": "...", "provider": "browser-web-speech", "note": "..." } }
```

The audio is kept regardless, so the interview can be re-transcribed later with
a better model.

### POST /evaluate → 200

Score one answer:

```json
{ "answer_id": 3 }
```

Or score every answer and close the interview:

```json
{ "interview_id": 1, "finalise": true }
```

```json
{
  "interview_id": 1,
  "finalised": true,
  "summary": {
    "overall": 68,
    "verdict": "Average - answer is there, delivery and depth are not",
    "headline": "68/100 for Full Stack Developer. Strongest: clarity (8.4/10). Weakest: structure (4.6/10).",
    "dimension_averages": { "relevance": 7.7, "depth": 7.3, "structure": 4.6,
                            "specificity": 5.5, "clarity": 8.4 },
    "by_category": { "behavioral": 63, "technical": 82, "situational": 54 },
    "strongest_dimension": "clarity",
    "weakest_dimension": "structure",
    "strengths": ["..."], "improvements": ["..."],
    "answered": 6, "total": 6
  }
}
```

`finalise: true` also writes the `reports` row.

### Other interview routes

| Method | Path | Notes |
|---|---|---|
| GET | `/interviews` | history, newest first |
| GET | `/interviews/{id}` | interview + questions + answers (used to resume a session) |
| DELETE | `/interviews/{id}` | 204, also deletes stored audio |

---

## Report

### GET /report → 200

`GET /report` returns your most recent completed interview.
`GET /report?interview_id=1` returns a specific one.

```json
{
  "interview": { "id": 1, "role_key": "full-stack-developer", "...": "..." },
  "overall_score": 68,
  "verdict": "Average - answer is there, delivery and depth are not",
  "headline": "68/100 for Full Stack Developer. ...",
  "dimension_averages": { "relevance": 7.7, "...": 0 },
  "by_category": { "technical": 82, "...": 0 },
  "strengths": ["..."],
  "improvements": ["..."],
  "answered": 6,
  "total": 6,
  "questions": [
    {
      "index": 1,
      "category": "behavioral",
      "question": "Tell me about a time you received hard feedback.",
      "expected_points": ["the feedback itself", "the initial reaction", "the concrete change made"],
      "transcript": "At the time I was three weeks into...",
      "code": "",
      "duration_sec": 58,
      "overall_score": 63,
      "scores": { "relevance": 7.3, "depth": 7.0, "structure": 6.0,
                  "specificity": 3.0, "clarity": 9.0 },
      "evaluation": {
        "reasons": { "relevance": "Covered 2/3 expected points." },
        "covered_points": ["the initial reaction", "the concrete change made"],
        "missed_points": ["the feedback itself"],
        "strengths": ["..."], "improvements": ["..."],
        "model_answer": "A strong answer covers: ...",
        "metrics": { "word_count": 101, "filler_count": 0, "words_per_minute": 104,
                     "pace": "good", "quantified_claims": 3 },
        "source": "heuristic"
      }
    }
  ]
}
```

404 with `"No interviews yet. Take a mock interview to get a report."` if there
are none.

---

## Roadmap

### GET /roadmap → 200

Returns the saved roadmap, generating one on first request.
409 with `"Analyse a resume first"` if there is no analysed resume to build from.

### POST /roadmap → 201

```json
{ "weeks": 8, "hours_per_week": 8 }
```

Both responses:

```json
{
  "id": 1,
  "role_key": "full-stack-developer",
  "week_count": 3,
  "hours_per_week": 8,
  "total_hours": 20,
  "coach_note": "This plan is 20 hours of work across 3 weeks, at 8 hours a week...",
  "weeks": [
    {
      "week": 1,
      "theme": "Focus: Structure every answer (STAR) + Put numbers and names in your answers",
      "hours": 8,
      "focus_skills": ["Structure every answer (STAR)", "..."],
      "outcome": "By Sunday: record a full mock interview and check that this week's drill actually shows up in how you answer.",
      "tasks": [
        { "skill": "Structure every answer (STAR)",
          "title": "Write out 6 STAR stories from your projects...",
          "url": "", "kind": "practice", "hours": 1, "priority": "high", "done": false }
      ]
    }
  ],
  "gaps": [
    { "skill": "Structure every answer (STAR)", "priority": "high", "kind": "interview-skill",
      "why": "Your mock interviews averaged 4.6/10 on structure. This costs you offers even when the technical answer is right.",
      "resources": [] }
  ],
  "progress": {}
}
```

`week_count` may be **less** than the `weeks` you requested — trailing empty
weeks are trimmed rather than padded.

### PATCH /roadmap/{id}/progress → 200

```json
{ "task_key": "1-0", "done": true }
```

`task_key` is `"<week>-<taskIndex>"`. Returns the updated roadmap.

---

## Reference data and dashboard

### GET /health (open)

```json
{
  "status": "ok",
  "version": "1.0.0",
  "llm": { "provider": "offline", "model": "", "available": false },
  "stt": { "effective": "none", "local_whisper_installed": false },
  "database": "sqlite"
}
```

### GET /roles (open) · GET /companies (open)

The role taxonomy and company interview styles used by the setup screen.

### GET /dashboard

Everything the dashboard needs in one call: counts, best and latest scores,
practice minutes, score trend, strongest/weakest dimension, recent interviews,
current resume, and whether a roadmap exists.

---

## Admin

All require `role == "admin"` (403 otherwise).

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/stats` | platform counts, engine status, and a `warnings` list (insecure `SECRET_KEY`, no LLM key, no server-side STT) |
| GET | `/admin/users` | accounts with resume and interview counts |
| PATCH | `/admin/users/{id}/active?active=false` | disable or enable an account; you cannot disable yourself |

Admins never receive resume text, transcripts or audio.
