import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Company, Health, ResumeSummary, Role } from '../lib/types'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { EmptyState, PageHeader, Spinner } from '../components/ui'

/** Modules 5 + 6 + 7: company/role selection, AI interview, coding interview. */
export default function InterviewSetup() {
  const { user } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const [roles, setRoles] = useState<Role[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [resumes, setResumes] = useState<ResumeSummary[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const [form, setForm] = useState({
    resume_id: null as number | null,
    role_key: user?.target_role ?? 'full-stack-developer',
    company_key: 'generic',
    mode: 'voice' as 'voice' | 'text' | 'coding',
    difficulty: 'medium' as 'easy' | 'medium' | 'hard',
    count: 6,
    coding_problems: 0,
  })

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)

    // allSettled, not all: a failing /resumes call must not blank out the role
    // and company pickers. Promise.all rejected the whole batch on any error,
    // which rendered the page as empty cards with no explanation.
    const [roleData, companyData, resumeList, healthData] = await Promise.allSettled([
      api.roles(), api.companies(), api.resumes(), api.health(),
    ])

    if (roleData.status === 'fulfilled') setRoles(roleData.value.roles)
    if (companyData.status === 'fulfilled') setCompanies(companyData.value.companies)
    if (healthData.status === 'fulfilled') setHealth(healthData.value)

    if (resumeList.status === 'fulfilled') {
      setResumes(resumeList.value)
      const primary = resumeList.value.find((resume) => resume.is_primary) ?? resumeList.value[0]
      if (primary) {
        setForm((current) => ({
          ...current,
          resume_id: primary.id,
          role_key: primary.role_key ?? current.role_key,
        }))
      }
    }

    // Roles and companies are what this page is FOR. Without them there is
    // nothing to choose, so that is a page-level failure, not a toast.
    const failure = [roleData, companyData].find((result) => result.status === 'rejected')
    if (failure && failure.status === 'rejected') {
      setLoadError((failure.reason as Error)?.message ?? 'Could not load interview options.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  async function start() {
    setStarting(true)
    try {
      const response = await api.generateQuestions(form)
      navigate(`/interview/${response.interview.id}`)
    } catch (error) {
      toast.error((error as Error).message)
      setStarting(false)
    }
  }

  if (loading) return <Spinner label="Loading interview options…" />

  if (loadError) {
    return (
      <>
        <PageHeader title="Set up your interview" />
        <EmptyState
          icon="🔌"
          title="Could not load interview options"
          body={loadError}
          action={<button className="btn-primary" onClick={() => void load()}>Try again</button>}
        />
      </>
    )
  }

  const selectedRole = roles.find((role) => role.key === form.role_key)
  const selectedCompany = companies.find((company) => company.key === form.company_key)
  const voiceReady = typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

  return (
    <>
      <PageHeader
        title="Set up your interview"
        subtitle="Pick the role and the company style. Questions are drawn from your resume where
                  we have one, so they are about your projects, not generic trivia."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,340px)]">
        <div className="space-y-6">
          {/* --- resume --- */}
          <section className="card">
            <h2 className="section-title mb-1">Resume</h2>
            <p className="muted mb-3">
              Questions about your own projects are the ones real interviewers ask.
            </p>
            {resumes.length === 0 ? (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                No resume uploaded. You can still practise with role-generic questions, but{' '}
                <Link to="/resume" className="font-semibold underline">uploading one</Link>{' '}
                makes the interview far more realistic.
              </div>
            ) : (
              <select className="input" value={form.resume_id ?? ''}
                      onChange={(e) => setForm({
                        ...form,
                        resume_id: e.target.value ? Number(e.target.value) : null,
                      })}>
                <option value="">No resume — generic questions</option>
                {resumes.map((resume) => (
                  <option key={resume.id} value={resume.id}>
                    {resume.filename}
                    {resume.ats_score !== null ? ` — ATS ${resume.ats_score}` : ''}
                  </option>
                ))}
              </select>
            )}
          </section>

          {/* --- role --- */}
          <section className="card">
            <h2 className="section-title mb-3">Target role</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {roles.map((role) => (
                <button key={role.key} onClick={() => setForm({ ...form, role_key: role.key })}
                        className={`rounded-xl border px-3.5 py-3 text-left transition ${
                          form.role_key === role.key
                            ? 'border-brand-500/60 bg-brand-500/10'
                            : 'border-ink-700 bg-ink-800/40 hover:border-ink-600'}`}>
                  <div className="text-sm font-semibold text-slate-100">{role.title}</div>
                  <div className="mt-0.5 truncate text-xs text-slate-500">
                    {role.must_have.slice(0, 4).join(' · ')}
                  </div>
                </button>
              ))}
            </div>
            {selectedRole && (
              <p className="mt-3 text-xs text-slate-500">
                This round probes: {selectedRole.focus.join(', ')}.
              </p>
            )}
          </section>

          {/* --- company style --- */}
          <section className="card">
            <h2 className="section-title mb-3">Company style</h2>
            <div className="space-y-2">
              {companies.map((company) => (
                <button key={company.key}
                        onClick={() => setForm({ ...form, company_key: company.key })}
                        className={`w-full rounded-xl border px-3.5 py-3 text-left transition ${
                          form.company_key === company.key
                            ? 'border-brand-500/60 bg-brand-500/10'
                            : 'border-ink-700 bg-ink-800/40 hover:border-ink-600'}`}>
                  <div className="text-sm font-semibold text-slate-100">{company.name}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{company.notes}</div>
                </button>
              ))}
            </div>
          </section>

          {/* --- format --- */}
          <section className="card">
            <h2 className="section-title mb-3">Format</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Answer with</label>
                <div className="flex gap-2">
                  {(['voice', 'text', 'coding'] as const).map((mode) => (
                    <button key={mode} onClick={() => setForm({ ...form, mode })}
                            className={`flex-1 rounded-xl border px-3 py-2 text-sm font-medium transition ${
                              form.mode === mode
                                ? 'border-brand-500/60 bg-brand-500/10 text-brand-400'
                                : 'border-ink-700 bg-ink-800/40 text-slate-300'}`}>
                      {mode === 'voice' ? '🎙️ Voice' : mode === 'text' ? '⌨️ Type' : '💻 Coding'}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Difficulty</label>
                <div className="flex gap-2">
                  {(['easy', 'medium', 'hard'] as const).map((level) => (
                    <button key={level} onClick={() => setForm({ ...form, difficulty: level })}
                            className={`flex-1 rounded-xl border px-3 py-2 text-sm font-medium capitalize transition ${
                              form.difficulty === level
                                ? 'border-brand-500/60 bg-brand-500/10 text-brand-400'
                                : 'border-ink-700 bg-ink-800/40 text-slate-300'}`}>
                      {level}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="label" htmlFor="count">Questions: {form.count}</label>
                <input id="count" type="range" min={3} max={15} value={form.count}
                       className="w-full accent-brand-500"
                       onChange={(e) => setForm({ ...form, count: Number(e.target.value) })} />
              </div>

              <div>
                <label className="label" htmlFor="coding">
                  Coding problems: {form.coding_problems}
                </label>
                <input id="coding" type="range" min={0} max={3} value={form.coding_problems}
                       className="w-full accent-brand-500"
                       onChange={(e) => setForm({
                         ...form, coding_problems: Number(e.target.value),
                       })} />
                <p className="mt-1 text-xs text-slate-500">
                  Added after the spoken questions.
                </p>
              </div>
            </div>

            {form.mode === 'voice' && !voiceReady && (
              <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                Live transcription needs Chrome or Edge. In this browser your audio is still
                recorded and transcribed on the server — you just will not see words appear
                as you speak.
              </div>
            )}
          </section>
        </div>

        {/* --- summary rail --- */}
        <aside className="lg:sticky lg:top-24 lg:h-fit">
          <section className="card">
            <h2 className="section-title mb-3">Your interview</h2>
            <dl className="space-y-2.5 text-sm">
              <Row label="Role" value={selectedRole?.title ?? form.role_key} />
              <Row label="Style" value={selectedCompany?.name ?? '—'} />
              <Row label="Mode" value={form.mode} />
              <Row label="Difficulty" value={form.difficulty} />
              <Row label="Questions"
                   value={`${form.count}${form.coding_problems
                     ? ` + ${form.coding_problems} coding` : ''}`} />
              <Row label="Est. time"
                   value={`~${Math.round((form.count * 3 + form.coding_problems * 12))} min`} />
            </dl>

            {selectedCompany && (
              <div className="mt-4 border-t border-ink-700 pt-4">
                <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                  Question mix
                </div>
                <div className="space-y-1.5">
                  {Object.entries(selectedCompany.mix)
                    .filter(([, weight]) => weight > 0)
                    .map(([category, weight]) => (
                      <div key={category} className="flex items-center gap-2">
                        <span className="w-24 text-xs capitalize text-slate-400">{category}</span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-700">
                          <div className="h-full rounded-full bg-brand-500"
                               style={{ width: `${(weight / 5) * 100}%` }} />
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            <button className="btn-primary mt-5 w-full" onClick={start} disabled={starting}>
              {starting ? 'Preparing questions…' : 'Start interview →'}
            </button>

            <p className="mt-3 text-xs text-slate-500">
              {health?.llm.available
                ? `Questions written by ${health.llm.model} from your resume.`
                : 'Running on the offline question bank — no API key configured.'}
            </p>
          </section>
        </aside>
      </div>
    </>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium capitalize text-slate-200">{value}</dd>
    </div>
  )
}
