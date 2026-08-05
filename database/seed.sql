-- ===========================================================================
--  Optional demo data for a PostgreSQL install.
--
--  Run AFTER schema.sql:
--      psql -d interviewace -f database/seed.sql
--
--  Accounts created (password for both is "DemoPass123"):
--      admin@interviewace.ai   - admin
--      demo@interviewace.ai    - candidate with one scored interview
--
--  The hash below is a real bcrypt hash of "DemoPass123", generated with
--  backend/app/security.py (sha256 pre-hash, then bcrypt cost 12). Regenerate
--  it for a different password with:
--
--      python -c "from backend.app.security import hash_password; print(hash_password('YourPassword'))"
--
--  It is safe to commit only because the password it protects is printed two
--  lines above it and these are throwaway demo accounts. Never seed a real
--  deployment this way.
-- ===========================================================================

BEGIN;

INSERT INTO users (email, password_hash, full_name, role, target_role, experience_level)
VALUES
  ('admin@interviewace.ai',
   '$2b$12$AYSpD.rgkdDrhVeCCzVxSOSCfyy8UfaDkJ3a5TaftO5DVis7YpP4e',
   'Platform Admin', 'admin', 'full-stack-developer', 'senior'),
  ('demo@interviewace.ai',
   '$2b$12$AYSpD.rgkdDrhVeCCzVxSOSCfyy8UfaDkJ3a5TaftO5DVis7YpP4e',
   'Demo Candidate', 'user', 'full-stack-developer', 'fresher')
ON CONFLICT (email) DO NOTHING;


-- A resume with a realistic ATS result attached.
INSERT INTO resumes (
    user_id, filename, stored_name, content_type, size_bytes,
    raw_text, skills, role_key, ats_score, ats_result, analyzed_at, is_primary
)
SELECT
    u.id,
    'demo_resume.txt',
    'seed_demo_resume.txt',
    'text/plain',
    1180,
    'Demo Candidate' || chr(10) ||
    'demo@interviewace.ai | +91 90000 00000' || chr(10) || chr(10) ||
    'EDUCATION' || chr(10) || 'B.Tech Computer Science, 2022-2026' || chr(10) || chr(10) ||
    'EXPERIENCE' || chr(10) ||
    'Backend Intern, Acme' || chr(10) || 'May 2025 - Jul 2025' || chr(10) ||
    '- Built 9 REST APIs in FastAPI over PostgreSQL, cutting p95 latency from 500ms to 140ms.' || chr(10) ||
    '- Wrote 60 pytest cases, raising coverage from 24% to 71%.' || chr(10) || chr(10) ||
    'SKILLS' || chr(10) ||
    'Python, JavaScript, React, FastAPI, PostgreSQL, Git, Docker, REST APIs, pytest',
    '["Docker","FastAPI","Git","JavaScript","PostgreSQL","Python","REST APIs","React","SQL","Testing"]'::jsonb,
    'full-stack-developer',
    78,
    '{"score": 78, "grade": "B+", "role_key": "full-stack-developer",
      "role_title": "Full Stack Developer",
      "band": "Good - passes most filters, room to sharpen",
      "missing_must_have": ["Node.js"],
      "missing_good_to_have": ["System Design", "CI/CD", "TypeScript"],
      "matched_skills": ["Docker","Git","JavaScript","PostgreSQL","REST APIs","React","SQL","Testing"],
      "extra_skills": ["FastAPI","Python"],
      "suggestions": ["Add evidence of Node.js - it is a core requirement for this role."]}'::jsonb,
    NOW(),
    TRUE
FROM users u
WHERE u.email = 'demo@interviewace.ai';


-- One completed interview, three questions, three scored answers, one report.
WITH candidate AS (
    SELECT id FROM users WHERE email = 'demo@interviewace.ai'
), new_interview AS (
    INSERT INTO interviews (user_id, resume_id, role_key, company_key, mode,
                            difficulty, status, completed_at, duration_sec, overall_score)
    SELECT c.id,
           (SELECT id FROM resumes WHERE user_id = c.id LIMIT 1),
           'full-stack-developer', 'product-startup', 'text', 'medium', 'completed',
           NOW(), 412, 71
    FROM candidate c
    RETURNING id, user_id
), new_questions AS (
    INSERT INTO questions (interview_id, index, category, skill, difficulty, text,
                           expected_points, time_limit_sec, source)
    SELECT i.id, q.index, q.category, q.skill, 'medium', q.text,
           q.points::jsonb, 180, 'bank'
    FROM new_interview i
    CROSS JOIN (VALUES
        (1, 'behavioral', NULL,
         'Tell me about a project you are proud of. What was your specific contribution?',
         '["situation and goal","what YOU did, not the team","the outcome","what you would change"]'),
        (2, 'technical', 'SQL',
         'A query that used to take 100ms now takes 8 seconds. How do you find out why?',
         '["EXPLAIN / query plan","missing or unusable index","data growth and statistics","N+1 from the app"]'),
        (3, 'technical', 'REST APIs',
         'How do you version an API without breaking existing clients?',
         '["URI or header versioning","additive changes only","deprecation window"]')
    ) AS q(index, category, skill, text, points)
    RETURNING id, interview_id, index
)
INSERT INTO answers (interview_id, question_id, transcript, transcript_source,
                     duration_sec, overall_score, scores, evaluation, evaluated_at)
SELECT
    nq.interview_id,
    nq.id,
    a.transcript,
    'typed',
    a.duration,
    a.score,
    a.scores::jsonb,
    jsonb_build_object('source', 'heuristic', 'overall', a.score,
                       'scores', a.scores::jsonb),
    NOW()
FROM new_questions nq
JOIN (VALUES
    (1, 'I built MediTrack, a booking tool for three clinics. I owned the backend: the schema, the FastAPI endpoints and the JWT auth. It handles about 400 bookings a month. If I rebuilt it I would add rate limiting from day one.',
     58.0, 68, '{"relevance": 7.5, "depth": 6.8, "structure": 6.5, "specificity": 7.0, "clarity": 8.5}'),
    (2, 'I would run EXPLAIN ANALYZE first to see the plan. Usually it has switched from an index scan to a sequential scan because the table grew and the statistics are stale, or the WHERE clause changed so the index no longer applies. I would also check for an N+1 pattern in the application.',
     71.0, 79, '{"relevance": 8.5, "depth": 8.0, "structure": 7.0, "specificity": 7.5, "clarity": 8.5}'),
    (3, 'Additive changes only, so existing fields never disappear. If a breaking change is unavoidable I put it behind a new version in the URI, keep the old one alive for a deprecation window, and log which clients are still calling it.',
     49.0, 66, '{"relevance": 7.5, "depth": 6.0, "structure": 7.0, "specificity": 6.0, "clarity": 8.0}')
) AS a(index, transcript, duration, score, scores) ON a.index = nq.index;


INSERT INTO reports (interview_id, user_id, overall_score, verdict,
                     dimension_averages, summary, strengths, improvements)
SELECT
    i.id, i.user_id, 71, 'Good - a few gaps to tighten',
    '{"relevance": 7.8, "depth": 6.9, "structure": 6.8, "specificity": 6.8, "clarity": 8.3}'::jsonb,
    '{"overall": 71, "answered": 3, "total": 3,
      "strongest_dimension": "clarity", "weakest_dimension": "specificity",
      "headline": "71/100 for Full Stack Developer. Strongest: clarity (8.3/10). Weakest: specificity (6.8/10)."}'::jsonb,
    '["Clear delivery with almost no filler words.","Named the exact tools and numbers on the backend question."]'::jsonb,
    '["Add a number to every result - 400 bookings is good, latency and uptime would be better.","Use STAR on behavioural questions; the Result is what gets remembered."]'::jsonb
FROM interviews i
JOIN users u ON u.id = i.user_id AND u.email = 'demo@interviewace.ai'
ORDER BY i.started_at DESC
LIMIT 1;

COMMIT;
