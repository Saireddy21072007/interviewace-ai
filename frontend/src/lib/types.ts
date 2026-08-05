/**
 * Types mirroring backend/app/schemas.py.
 *
 * They are written by hand rather than generated, so that a backend change
 * that breaks the contract shows up as a TypeScript error here instead of as
 * `undefined` in the browser at demo time.
 */

export type ExperienceLevel = 'fresher' | 'junior' | 'mid' | 'senior'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type InterviewMode = 'voice' | 'text' | 'coding'
export type QuestionCategory = 'technical' | 'behavioral' | 'situational' | 'resume' | 'coding'

export interface User {
  id: number
  email: string
  full_name: string
  role: 'user' | 'admin'
  target_role: string
  experience_level: string
  created_at: string
  last_login_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in_minutes: number
  user: User
}

export interface ResumeSummary {
  id: number
  filename: string
  size_bytes: number
  skills: string[]
  ats_score: number | null
  role_key: string | null
  is_primary: boolean
  created_at: string
  analyzed_at: string | null
}

export interface ResumeDetail extends ResumeSummary {
  parsed: ParsedResume
  ats_result: Record<string, unknown>
  job_description: string
}

export interface ParsedResume {
  ok?: boolean
  warnings?: string[]
  contact?: {
    name: string | null
    email: string | null
    phone: string | null
    linkedin: string | null
    github: string | null
  }
  section_names?: string[]
  skill_list?: string[]
  experience_years?: number
  signals?: {
    word_count: number
    bullet_count: number
    action_verbs: string[]
    weak_phrases: string[]
    quantified_results: number
    estimated_pages: number
  }
}

export interface UploadResumeResponse {
  resume: ResumeDetail
  warnings: string[]
  detected_skills: string[]
  message: string
}

export interface ScoreBreakdown {
  name: string
  key: string
  score: number
  max: number
  detail: string
  suggestions?: string[]
  matched?: string[]
  missing?: string[]
  matched_must_have?: string[]
  missing_must_have?: string[]
}

export interface AtsResult {
  resume_id: number
  score: number
  grade: string
  band: string
  role_key: string
  role_title: string
  breakdown: ScoreBreakdown[]
  matched_skills: string[]
  missing_must_have: string[]
  missing_good_to_have: string[]
  extra_skills: string[]
  suggestions: string[]
  review: {
    verdict?: string
    one_line?: string
    strengths?: string[]
    fixes?: (string | { issue: string; rewrite: string })[]
  }
  warnings: string[]
}

export interface CodingProblem {
  slug?: string
  title?: string
  examples?: { input: string; output: string }[]
  starter_code?: string
}

export interface Question {
  id: number
  index: number
  category: QuestionCategory
  skill: string | null
  difficulty: Difficulty
  text: string
  time_limit_sec: number
  source: 'bank' | 'llm'
  problem: CodingProblem
}

export interface Interview {
  id: number
  role_key: string
  company_key: string
  mode: string
  difficulty: string
  status: 'in_progress' | 'completed' | 'abandoned'
  started_at: string
  completed_at: string | null
  duration_sec: number
  overall_score: number | null
}

export interface RubricScores {
  relevance: number
  depth: number
  structure: number
  specificity: number
  clarity: number
}

export interface Evaluation {
  scores?: RubricScores
  reasons?: Record<string, string>
  covered_points?: string[]
  missed_points?: string[]
  strengths?: string[]
  improvements?: string[]
  model_answer?: string
  verdict?: string
  overall?: number
  source?: 'llm' | 'heuristic'
  metrics?: {
    word_count: number
    filler_count: number
    filler_rate: number
    quantified_claims: number
    duration_sec?: number
    words_per_minute?: number
    pace?: string
  }
  static_checks?: { name: string; passed: boolean; detail: string }[]
  note?: string
  complexity?: string
}

export interface Answer {
  id: number
  question_id: number
  transcript: string
  transcript_source: string
  duration_sec: number | null
  code: string
  language: string
  overall_score: number | null
  scores: Partial<RubricScores>
  evaluation: Evaluation
  created_at: string
}

export interface SubmitAnswerResponse {
  answer: Answer
  transcription: { text?: string; provider?: string; note?: string }
  next_question: Question | null
  answered: number
  total: number
}

export interface InterviewSummary {
  overall: number
  verdict: string
  headline: string
  dimension_averages: RubricScores
  by_category: Record<string, number>
  strongest_dimension?: string
  weakest_dimension?: string
  strengths: string[]
  improvements: string[]
  answered: number
  total: number
}

export interface ReportQuestion {
  index: number
  category: QuestionCategory
  skill: string | null
  difficulty: string
  question: string
  expected_points: string[]
  transcript: string
  code: string
  duration_sec: number | null
  overall_score: number | null
  scores: Partial<RubricScores>
  evaluation: Evaluation
}

export interface Report {
  interview: Interview
  overall_score: number
  verdict: string
  headline: string
  dimension_averages: Partial<RubricScores>
  by_category: Record<string, number>
  strengths: string[]
  improvements: string[]
  answered: number
  total: number
  questions: ReportQuestion[]
  created_at: string | null
}

export interface RoadmapTask {
  skill: string
  title: string
  url: string
  kind: 'course' | 'reading' | 'practice' | 'project'
  hours: number
  priority: 'critical' | 'high' | 'medium' | 'low'
  done: boolean
}

export interface RoadmapWeek {
  week: number
  theme: string
  tasks: RoadmapTask[]
  hours: number
  focus_skills: string[]
  outcome: string
}

export interface Gap {
  skill: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  kind: string
  why: string
  resources: { title: string; url: string; kind: string; hours: number }[]
}

export interface Roadmap {
  id: number
  role_key: string
  week_count: number
  hours_per_week: number
  total_hours: number
  coach_note: string
  weeks: RoadmapWeek[]
  gaps: Gap[]
  progress: Record<string, boolean>
  created_at: string
  updated_at: string
}

export interface DashboardStats {
  resumes: number
  interviews_started: number
  interviews_completed: number
  questions_answered: number
  best_ats_score: number | null
  latest_ats_score: number | null
  average_interview_score: number | null
  best_interview_score: number | null
  practice_minutes: number
  score_trend: { interview_id: number; date: string; score: number; role: string }[]
  weakest_dimension: string | null
  strongest_dimension: string | null
  recent_interviews: Interview[]
  latest_resume: ResumeSummary | null
  has_roadmap: boolean
}

export interface Role {
  key: string
  title: string
  family: string
  must_have: string[]
  good_to_have: string[]
  focus: string[]
}

export interface Company {
  key: string
  name: string
  notes: string
  mix: Record<string, number>
}

export interface Health {
  status: string
  app: string
  version: string
  llm: { provider: string; model: string; available: boolean }
  stt: { effective: string; local_whisper_installed: boolean }
  database: string
}

export interface AdminStats {
  users: number
  active_users_7d: number
  resumes: number
  interviews: number
  completed_interviews: number
  answers: number
  average_ats_score: number | null
  average_interview_score: number | null
  llm: Health['llm']
  stt: Health['stt']
  database: string
  warnings: string[]
}

export interface AdminUserRow {
  id: number
  email: string
  full_name: string
  role: string
  target_role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
  resume_count: number
  interview_count: number
}
