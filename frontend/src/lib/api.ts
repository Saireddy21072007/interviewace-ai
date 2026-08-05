/**
 * The single place the frontend talks to the backend.
 *
 * Every call goes through `request()`, which means auth headers, JSON parsing
 * and error handling are written once. Two behaviours matter:
 *
 *  - Errors always surface the backend's `detail` string. The API is written
 *    to put a sentence a candidate can act on in that field, so components can
 *    show `error.message` directly without translating anything.
 *  - A 401 clears the stored token and bounces to /login, so an expired
 *    session cannot leave the UI stuck showing spinners forever.
 */

import type {
  AdminStats, AdminUserRow, Answer, AtsResult, Company, DashboardStats, Health,
  Interview, InterviewSummary, Question, Report, Roadmap, ResumeDetail,
  ResumeSummary, Role, SubmitAnswerResponse, TokenResponse, User,
} from './types'

const BASE = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'interviewace.token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Options = {
  method?: string
  body?: unknown
  formData?: FormData
  auth?: boolean
  signal?: AbortSignal
}

async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { method = 'GET', body, formData, auth = true, signal } = options
  const headers: Record<string, string> = {}

  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  // Do NOT set Content-Type for FormData: the browser has to add the
  // multipart boundary itself, and setting it manually breaks the upload.
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    })
  } catch {
    // Do NOT name a specific server here. A failed fetch means the request did
    // not complete - which is equally true when the API is down and when the
    // dev server proxying to it is down. Blaming port 8000 sent a real
    // debugging session in the wrong direction while the API was healthy.
    throw new ApiError(
      'Cannot reach the API. Check that both servers are running - "run.bat" starts them.',
      0,
    )
  }

  if (response.status === 401 && auth) {
    clearToken()
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login?expired=1'
    }
    throw new ApiError('Your session expired. Please sign in again.', 401)
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail =
      (payload as { detail?: unknown })?.detail ?? `Request failed (${response.status})`
    throw new ApiError(
      typeof detail === 'string' ? detail : JSON.stringify(detail),
      response.status,
    )
  }
  return payload as T
}

export const api = {
  // --- auth ---
  register: (data: {
    email: string; password: string; full_name?: string
    target_role?: string; experience_level?: string
  }) => request<TokenResponse>('/register', { method: 'POST', body: data, auth: false }),

  login: (email: string, password: string) =>
    request<TokenResponse>('/login', { method: 'POST', body: { email, password }, auth: false }),

  me: () => request<User>('/me'),

  updateMe: (data: Partial<Pick<User, 'full_name' | 'target_role' | 'experience_level'>>) =>
    request<User>('/me', { method: 'PATCH', body: data }),

  changePassword: (current_password: string, new_password: string) =>
    request<void>('/me/password', { method: 'POST', body: { current_password, new_password } }),

  // --- reference data ---
  health: () => request<Health>('/health', { auth: false }),
  roles: () => request<{ roles: Role[]; skills: string[]; experience_levels: string[] }>('/roles',
    { auth: false }),
  companies: () => request<{ companies: Company[] }>('/companies', { auth: false }),

  // --- dashboard ---
  dashboard: () => request<DashboardStats>('/dashboard'),

  // --- resumes ---
  uploadResume: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('make_primary', 'true')
    return request<{
      resume: ResumeDetail; warnings: string[]; detected_skills: string[]; message: string
    }>('/upload-resume', { method: 'POST', formData: form })
  },

  analyzeResume: (data: {
    resume_id?: number; role_key?: string; job_description?: string; experience_level?: string
  }) => request<AtsResult>('/analyze-resume', { method: 'POST', body: data }),

  resumes: () => request<ResumeSummary[]>('/resumes'),
  resume: (id: number) => request<ResumeDetail>(`/resumes/${id}`),
  resumeText: (id: number) =>
    request<{ resume_id: number; filename: string; text: string }>(`/resumes/${id}/text`),
  deleteResume: (id: number) => request<void>(`/resumes/${id}`, { method: 'DELETE' }),

  // --- interviews ---
  generateQuestions: (data: {
    resume_id?: number | null; role_key?: string; company_key?: string
    mode?: string; difficulty?: string; count?: number; coding_problems?: number
  }) => request<{ interview: Interview; questions: Question[]; engine: string }>(
    '/generate-questions', { method: 'POST', body: data }),

  submitAnswer: (data: {
    question_id: number; transcript?: string; duration_sec?: number | null
    code?: string; language?: string; evaluate_now?: boolean
  }) => request<SubmitAnswerResponse>('/submit-answer', { method: 'POST', body: data }),

  submitAudioAnswer: (data: {
    question_id: number; audio: Blob; browser_transcript: string
    duration_sec: number; evaluate_now?: boolean
  }) => {
    const form = new FormData()
    form.append('question_id', String(data.question_id))
    form.append('audio', data.audio, 'answer.webm')
    form.append('browser_transcript', data.browser_transcript)
    form.append('duration_sec', String(Math.round(data.duration_sec)))
    form.append('evaluate_now', String(data.evaluate_now ?? true))
    return request<SubmitAnswerResponse>('/submit-answer/audio', { method: 'POST', formData: form })
  },

  finaliseInterview: (interview_id: number) =>
    request<{ interview_id: number; finalised: boolean; summary: InterviewSummary }>(
      '/evaluate', { method: 'POST', body: { interview_id, finalise: true } }),

  reEvaluateAnswer: (answer_id: number) =>
    request<{ answer: Answer }>('/evaluate', { method: 'POST', body: { answer_id } }),

  interviews: () => request<Interview[]>('/interviews'),
  interview: (id: number) =>
    request<{ interview: Interview; questions: Question[]; answers: Answer[] }>(`/interviews/${id}`),
  deleteInterview: (id: number) => request<void>(`/interviews/${id}`, { method: 'DELETE' }),

  // --- report + roadmap ---
  report: (interviewId?: number) =>
    request<Report>(`/report${interviewId ? `?interview_id=${interviewId}` : ''}`),

  roadmap: () => request<Roadmap>('/roadmap'),
  createRoadmap: (data: { weeks?: number; hours_per_week?: number; role_key?: string }) =>
    request<Roadmap>('/roadmap', { method: 'POST', body: data }),
  setTaskDone: (roadmapId: number, task_key: string, done: boolean) =>
    request<Roadmap>(`/roadmap/${roadmapId}/progress`, { method: 'PATCH', body: { task_key, done } }),

  // --- admin ---
  adminStats: () => request<AdminStats>('/admin/stats'),
  adminUsers: () => request<AdminUserRow[]>('/admin/users'),
  adminSetActive: (userId: number, active: boolean) =>
    request<AdminUserRow>(`/admin/users/${userId}/active?active=${active}`, { method: 'PATCH' }),
}
