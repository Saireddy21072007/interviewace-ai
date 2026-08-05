-- ===========================================================================
--  InterviewAce AI - PostgreSQL schema
--
--  The application creates its tables automatically through SQLAlchemy
--  (backend/app/models.py), so you never HAVE to run this file. It exists for
--  two reasons:
--
--    1. The project report needs the schema in plain SQL, not in Python.
--    2. Production DBAs review DDL, not ORM models.
--
--  This is the same schema models.py produces, with two deliberate upgrades
--  that SQLAlchemy's portable types cannot express: JSONB instead of JSON
--  (indexable and stored binary), and CHECK constraints on the enum-like
--  columns.
--
--  Usage:
--      createdb interviewace
--      psql -d interviewace -f database/schema.sql
--      psql -d interviewace -f database/seed.sql      -- optional demo data
--
--  Then in .env:
--      DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/interviewace
-- ===========================================================================

BEGIN;

DROP TABLE IF EXISTS roadmaps  CASCADE;
DROP TABLE IF EXISTS reports   CASCADE;
DROP TABLE IF EXISTS answers   CASCADE;
DROP TABLE IF EXISTS questions CASCADE;
DROP TABLE IF EXISTS interviews CASCADE;
DROP TABLE IF EXISTS resumes   CASCADE;
DROP TABLE IF EXISTS users     CASCADE;


-- ---------------------------------------------------------------------------
-- 1. users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id                SERIAL PRIMARY KEY,
    email             VARCHAR(255) NOT NULL UNIQUE,
    -- bcrypt hash of a sha256 pre-hash. Never a plaintext or reversible value.
    password_hash     VARCHAR(255) NOT NULL,
    full_name         VARCHAR(120) NOT NULL DEFAULT '',
    role              VARCHAR(20)  NOT NULL DEFAULT 'user',
    target_role       VARCHAR(60)  NOT NULL DEFAULT 'full-stack-developer',
    experience_level  VARCHAR(20)  NOT NULL DEFAULT 'fresher',
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at     TIMESTAMPTZ,

    CONSTRAINT users_role_check  CHECK (role IN ('user', 'admin')),
    CONSTRAINT users_level_check CHECK (experience_level IN ('fresher','junior','mid','senior')),
    CONSTRAINT users_email_check CHECK (POSITION('@' IN email) > 1)
);

CREATE INDEX ix_users_email      ON users (LOWER(email));
CREATE INDEX ix_users_last_login ON users (last_login_at DESC);


-- ---------------------------------------------------------------------------
-- 2. resumes
--    `parsed` and `ats_result` hold analysis output owned by the ai/ package.
--    They are JSONB rather than columns because their shape changes every time
--    the model improves; a migration per tweak would couple the AI team's
--    iteration speed to the database.
-- ---------------------------------------------------------------------------
CREATE TABLE resumes (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    filename         VARCHAR(255) NOT NULL,
    stored_name      VARCHAR(255) NOT NULL,   -- generated; never the user's own name
    content_type     VARCHAR(120) NOT NULL DEFAULT '',
    size_bytes       INTEGER      NOT NULL DEFAULT 0,

    raw_text         TEXT   NOT NULL DEFAULT '',
    parsed           JSONB  NOT NULL DEFAULT '{}'::jsonb,
    skills           JSONB  NOT NULL DEFAULT '[]'::jsonb,

    role_key         VARCHAR(60),
    job_description  TEXT    NOT NULL DEFAULT '',
    ats_score        INTEGER,
    ats_result       JSONB   NOT NULL DEFAULT '{}'::jsonb,
    analyzed_at      TIMESTAMPTZ,

    is_primary       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT resumes_score_range CHECK (ats_score IS NULL OR ats_score BETWEEN 0 AND 100)
);

CREATE INDEX ix_resumes_user_created ON resumes (user_id, created_at DESC);
CREATE INDEX ix_resumes_ats_score    ON resumes (ats_score);
-- Lets "which candidates know Kubernetes?" run without scanning every row.
CREATE INDEX ix_resumes_skills_gin   ON resumes USING GIN (skills);


-- ---------------------------------------------------------------------------
-- 3. interviews
--    resume_id is SET NULL, not CASCADE: deleting a resume must not erase the
--    interview history built on it.
-- ---------------------------------------------------------------------------
CREATE TABLE interviews (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
    resume_id      INTEGER          REFERENCES resumes(id) ON DELETE SET NULL,

    role_key       VARCHAR(60) NOT NULL DEFAULT 'full-stack-developer',
    company_key    VARCHAR(60) NOT NULL DEFAULT 'generic',
    mode           VARCHAR(20) NOT NULL DEFAULT 'voice',
    difficulty     VARCHAR(20) NOT NULL DEFAULT 'medium',
    status         VARCHAR(20) NOT NULL DEFAULT 'in_progress',

    started_at     TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    completed_at   TIMESTAMPTZ,
    duration_sec   DOUBLE PRECISION NOT NULL DEFAULT 0,
    overall_score  INTEGER,

    CONSTRAINT interviews_mode_check   CHECK (mode IN ('voice','text','coding')),
    CONSTRAINT interviews_diff_check   CHECK (difficulty IN ('easy','medium','hard')),
    CONSTRAINT interviews_status_check CHECK (status IN ('in_progress','completed','abandoned')),
    CONSTRAINT interviews_score_range  CHECK (overall_score IS NULL OR overall_score BETWEEN 0 AND 100),
    -- An interview cannot finish before it started.
    CONSTRAINT interviews_time_order   CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX ix_interviews_user_status ON interviews (user_id, status);
CREATE INDEX ix_interviews_started     ON interviews (started_at DESC);


-- ---------------------------------------------------------------------------
-- 4. questions
--    expected_points is the mark scheme. The API hides it while the interview
--    is running and returns it in the report afterwards.
-- ---------------------------------------------------------------------------
CREATE TABLE questions (
    id              SERIAL PRIMARY KEY,
    interview_id    INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,

    index           INTEGER     NOT NULL DEFAULT 1,
    category        VARCHAR(30) NOT NULL DEFAULT 'technical',
    skill           VARCHAR(60),
    difficulty      VARCHAR(20) NOT NULL DEFAULT 'medium',
    text            TEXT        NOT NULL,
    expected_points JSONB       NOT NULL DEFAULT '[]'::jsonb,
    time_limit_sec  INTEGER     NOT NULL DEFAULT 180,
    source          VARCHAR(20) NOT NULL DEFAULT 'bank',
    problem         JSONB       NOT NULL DEFAULT '{}'::jsonb,   -- coding rounds only

    CONSTRAINT uq_question_per_interview UNIQUE (interview_id, index),
    CONSTRAINT questions_category_check CHECK (
        category IN ('technical','behavioral','situational','resume','coding')),
    CONSTRAINT questions_source_check CHECK (source IN ('bank','llm'))
);

CREATE INDEX ix_questions_interview ON questions (interview_id, index);


-- ---------------------------------------------------------------------------
-- 5. answers
--    UNIQUE on question_id enforces one answer per question at the database
--    level. Re-answering overwrites; without this constraint a candidate who
--    redoes a question would be counted twice in the report average.
-- ---------------------------------------------------------------------------
CREATE TABLE answers (
    id                SERIAL PRIMARY KEY,
    interview_id      INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    question_id       INTEGER NOT NULL UNIQUE REFERENCES questions(id) ON DELETE CASCADE,

    transcript        TEXT        NOT NULL DEFAULT '',
    transcript_source VARCHAR(30) NOT NULL DEFAULT 'typed',
    audio_path        VARCHAR(255),
    duration_sec      DOUBLE PRECISION,

    code              TEXT        NOT NULL DEFAULT '',
    language          VARCHAR(20) NOT NULL DEFAULT 'python',

    overall_score     INTEGER,
    scores            JSONB NOT NULL DEFAULT '{}'::jsonb,   -- the five rubric dimensions
    evaluation        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- full evaluator output
    evaluated_at      TIMESTAMPTZ,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT answers_score_range CHECK (overall_score IS NULL OR overall_score BETWEEN 0 AND 100)
);

CREATE INDEX ix_answers_interview ON answers (interview_id);


-- ---------------------------------------------------------------------------
-- 6. reports  (one per interview)
-- ---------------------------------------------------------------------------
CREATE TABLE reports (
    id                 SERIAL PRIMARY KEY,
    interview_id       INTEGER NOT NULL UNIQUE REFERENCES interviews(id) ON DELETE CASCADE,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    overall_score      INTEGER      NOT NULL DEFAULT 0,
    verdict            VARCHAR(120) NOT NULL DEFAULT '',
    dimension_averages JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary            JSONB NOT NULL DEFAULT '{}'::jsonb,
    strengths          JSONB NOT NULL DEFAULT '[]'::jsonb,
    improvements       JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT reports_score_range CHECK (overall_score BETWEEN 0 AND 100)
);

CREATE INDEX ix_reports_user ON reports (user_id, created_at DESC);


-- ---------------------------------------------------------------------------
-- 7. roadmaps
-- ---------------------------------------------------------------------------
CREATE TABLE roadmaps (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id)      ON DELETE CASCADE,
    resume_id      INTEGER          REFERENCES resumes(id)    ON DELETE SET NULL,
    interview_id   INTEGER          REFERENCES interviews(id) ON DELETE SET NULL,

    role_key       VARCHAR(60) NOT NULL DEFAULT 'full-stack-developer',
    week_count     INTEGER     NOT NULL DEFAULT 8,
    hours_per_week INTEGER     NOT NULL DEFAULT 8,
    total_hours    INTEGER     NOT NULL DEFAULT 0,
    coach_note     TEXT        NOT NULL DEFAULT '',

    weeks          JSONB NOT NULL DEFAULT '[]'::jsonb,
    gaps           JSONB NOT NULL DEFAULT '[]'::jsonb,
    progress       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {"<week>-<taskIndex>": true}

    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT roadmaps_weeks_range CHECK (week_count BETWEEN 1 AND 24),
    CONSTRAINT roadmaps_hours_range CHECK (hours_per_week BETWEEN 1 AND 40)
);

CREATE INDEX ix_roadmaps_user ON roadmaps (user_id, created_at DESC);


-- ---------------------------------------------------------------------------
-- Keep roadmaps.updated_at honest without relying on the application.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER roadmaps_touch_updated_at
    BEFORE UPDATE ON roadmaps
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ---------------------------------------------------------------------------
-- Views used by the admin console.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_user_activity AS
SELECT
    u.id,
    u.email,
    u.full_name,
    u.role,
    u.target_role,
    u.is_active,
    u.created_at,
    u.last_login_at,
    COUNT(DISTINCT r.id) AS resume_count,
    COUNT(DISTINCT i.id) AS interview_count,
    MAX(r.ats_score)     AS best_ats_score,
    MAX(i.overall_score) AS best_interview_score
FROM users u
LEFT JOIN resumes    r ON r.user_id = u.id
LEFT JOIN interviews i ON i.user_id = u.id
GROUP BY u.id;

COMMIT;
