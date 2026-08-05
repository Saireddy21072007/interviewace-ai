import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { AtsResult, ResumeSummary, Role } from '../lib/types'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Chip, PageHeader, ScoreBar, ScoreRing, Spinner } from '../components/ui'
import { formatBytes, formatDate } from '../lib/format'

/**
 * Modules 3 and 4: Resume Upload + Resume Analyzer.
 *
 * The two halves of the page mirror the two API calls. Upload is instant and
 * shows what the parser saw; analysis is a separate action because the same
 * resume gets scored against several different roles and job descriptions.
 */
export default function ResumePage() {
  const { user } = useAuth()
  const toast = useToast()
  const fileInput = useRef<HTMLInputElement>(null)

  const [resumes, setResumes] = useState<ResumeSummary[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [roles, setRoles] = useState<Role[]>([])
  const [roleKey, setRoleKey] = useState(user?.target_role ?? 'full-stack-developer')
  const [level, setLevel] = useState(user?.experience_level ?? 'fresher')
  const [jobDescription, setJobDescription] = useState('')
  const [result, setResult] = useState<AtsResult | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [analysing, setAnalysing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [dragOver, setDragOver] = useState(false)

  const loadResumes = useCallback(async () => {
    const list = await api.resumes()
    setResumes(list)
    setSelectedId((current) => current ?? list[0]?.id ?? null)
    return list
  }, [])

  useEffect(() => {
    Promise.all([loadResumes(), api.roles()])
      .then(([, roleData]) => setRoles(roleData.roles))
      .catch((error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [loadResumes, toast])

  async function upload(file: File) {
    setUploading(true)
    setResult(null)
    setPreview(null)
    try {
      const response = await api.uploadResume(file)
      toast.success(response.message)
      response.warnings.forEach((warning) => toast.push(warning, 'error'))
      await loadResumes()
      setSelectedId(response.resume.id)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function analyse() {
    if (!selectedId) return
    setAnalysing(true)
    try {
      const response = await api.analyzeResume({
        resume_id: selectedId, role_key: roleKey,
        job_description: jobDescription, experience_level: level,
      })
      setResult(response)
      await loadResumes()
      toast.success(`Scored ${response.score}/100 for ${response.role_title}.`)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setAnalysing(false)
    }
  }

  async function showPreview() {
    if (!selectedId) return
    try {
      const response = await api.resumeText(selectedId)
      setPreview(response.text)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteResume(id)
      const list = await loadResumes()
      if (selectedId === id) {
        setSelectedId(list[0]?.id ?? null)
        setResult(null)
      }
      toast.success('Resume deleted.')
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  if (loading) return <Spinner label="Loading your resumes…" />

  const selected = resumes.find((resume) => resume.id === selectedId) ?? null

  return (
    <>
      <PageHeader
        title="Resume analyzer"
        subtitle="Upload your resume, pick the role you are targeting, and see the score an
                  applicant-tracking system would give it — with the reason for every point."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
        {/* ---------------- left: upload + list + controls ---------------- */}
        <div className="space-y-6">
          <section className="card">
            <h2 className="section-title mb-3">Upload</h2>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                const file = e.dataTransfer.files?.[0]
                if (file) upload(file)
              }}
              onClick={() => fileInput.current?.click()}
              className={`cursor-pointer rounded-xl border-2 border-dashed px-4 py-8 text-center transition
                ${dragOver ? 'border-brand-500 bg-brand-500/10' : 'border-ink-600 hover:border-brand-500/60'}`}
            >
              <div className="text-3xl">{uploading ? '⏳' : '📄'}</div>
              <p className="mt-2 text-sm font-medium text-slate-200">
                {uploading ? 'Reading your resume…' : 'Drop a file or click to browse'}
              </p>
              <p className="mt-1 text-xs text-slate-500">PDF, DOCX or TXT · max 10MB</p>
              <input ref={fileInput} type="file" accept=".pdf,.docx,.txt,.md" className="hidden"
                     onChange={(e) => {
                       const file = e.target.files?.[0]
                       if (file) upload(file)
                       e.target.value = ''
                     }} />
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Tip: export a text-based PDF, not a scan. If a parser cannot read it, neither can
              a recruiter’s software.
            </p>
          </section>

          {resumes.length > 0 && (
            <section className="card">
              <h2 className="section-title mb-3">Your resumes</h2>
              <ul className="space-y-2">
                {resumes.map((resume) => (
                  <li key={resume.id}>
                    <button
                      onClick={() => { setSelectedId(resume.id); setResult(null); setPreview(null) }}
                      className={`w-full rounded-xl border px-3 py-2.5 text-left transition ${
                        resume.id === selectedId
                          ? 'border-brand-500/60 bg-brand-500/10'
                          : 'border-ink-700 bg-ink-800/40 hover:border-ink-600'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium text-slate-100">
                          {resume.filename}
                        </span>
                        {resume.ats_score !== null && (
                          <Chip className="border-brand-500/30 bg-brand-500/10 text-brand-400">
                            {resume.ats_score}
                          </Chip>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                        <span>{formatDate(resume.created_at)}</span>
                        <span>·</span>
                        <span>{formatBytes(resume.size_bytes)}</span>
                        <span>·</span>
                        <span>{resume.skills.length} skills</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
              {selected && (
                <div className="mt-3 flex gap-2">
                  <button className="btn-ghost flex-1 !py-2" onClick={showPreview}>
                    Preview parsed text
                  </button>
                  <button className="btn-danger !px-3 !py-2" onClick={() => remove(selected.id)}>
                    Delete
                  </button>
                </div>
              )}
            </section>
          )}

          {selected && (
            <section className="card">
              <h2 className="section-title mb-3">Target</h2>
              <div className="space-y-4">
                <div>
                  <label className="label" htmlFor="role">Role</label>
                  <select id="role" className="input" value={roleKey}
                          onChange={(e) => setRoleKey(e.target.value)}>
                    {roles.map((role) => (
                      <option key={role.key} value={role.key}>{role.title}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="level">Experience level</label>
                  <select id="level" className="input" value={level}
                          onChange={(e) => setLevel(e.target.value)}>
                    <option value="fresher">Fresher / student</option>
                    <option value="junior">0-2 years</option>
                    <option value="mid">2-5 years</option>
                    <option value="senior">5+ years</option>
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="jd">
                    Job description <span className="font-normal text-slate-500">(optional)</span>
                  </label>
                  <textarea id="jd" rows={5} className="input resize-y"
                            placeholder="Paste the posting here to score keyword overlap against it."
                            value={jobDescription}
                            onChange={(e) => setJobDescription(e.target.value)} />
                  <p className="mt-1 text-xs text-slate-500">
                    With a posting, 15 of the 100 points measure how well your wording matches it.
                  </p>
                </div>
                <button className="btn-primary w-full" onClick={analyse} disabled={analysing}>
                  {analysing ? 'Analysing…' : 'Analyse resume'}
                </button>
              </div>
            </section>
          )}
        </div>

        {/* ---------------- right: results ---------------- */}
        <div className="space-y-6">
          {preview && (
            <section className="card">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="section-title">What the parser read</h2>
                <button className="btn-ghost !px-3 !py-1.5" onClick={() => setPreview(null)}>
                  Close
                </button>
              </div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-ink-950/70 p-4
                              font-mono text-xs leading-relaxed text-slate-400">
                {preview || '(no text could be extracted)'}
              </pre>
            </section>
          )}

          {!result ? (
            <section className="card flex flex-col items-center gap-3 py-16 text-center">
              <div className="text-4xl">📊</div>
              <h3 className="text-lg font-semibold text-white">No analysis yet</h3>
              <p className="max-w-sm text-sm text-slate-400">
                {resumes.length === 0
                  ? 'Upload a resume to get started.'
                  : 'Pick a target role on the left and hit “Analyse resume”.'}
              </p>
            </section>
          ) : (
            <AtsReport result={result} />
          )}
        </div>
      </div>
    </>
  )
}

function AtsReport({ result }: { result: AtsResult }) {
  return (
    <>
      <section className="card">
        <div className="flex flex-wrap items-center gap-6">
          <ScoreRing score={result.score} />
          <div className="min-w-[220px] flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white">{result.role_title}</h2>
              <Chip className="border-brand-500/30 bg-brand-500/10 text-brand-400">
                Grade {result.grade}
              </Chip>
            </div>
            <p className="mt-1 text-sm text-slate-300">{result.band}</p>
            {result.review?.one_line && (
              <p className="mt-3 rounded-xl border border-ink-700 bg-ink-800/50 px-3.5 py-2.5 text-sm text-slate-300">
                {result.review.one_line}
              </p>
            )}
          </div>
        </div>

        {result.warnings.length > 0 && (
          <ul className="mt-4 space-y-2">
            {result.warnings.map((warning) => (
              <li key={warning}
                  className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-200">
                ⚠ {warning}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h3 className="section-title mb-1">Where the points went</h3>
        <p className="muted mb-4">Every sub-score is a rule, not an opinion. Same resume, same number.</p>
        <div className="space-y-5">
          {result.breakdown.map((part) => (
            <div key={part.key}>
              <ScoreBar label={part.name} score={part.score} max={part.max} detail={part.detail} />
              {part.suggestions && part.suggestions.length > 0 && (
                <ul className="mt-2 space-y-1.5 pl-1">
                  {part.suggestions.map((suggestion) => (
                    <li key={suggestion} className="flex gap-2 text-xs text-slate-400">
                      <span className="text-brand-400">→</span>{suggestion}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h3 className="section-title mb-3">Skills</h3>
        <SkillGroup title="Matched" tone="emerald" skills={result.matched_skills} />
        <SkillGroup title="Missing — required" tone="rose" skills={result.missing_must_have}
                    note="A keyword filter will drop the resume without these." />
        <SkillGroup title="Missing — preferred" tone="amber" skills={result.missing_good_to_have} />
        <SkillGroup title="Extra breadth" tone="slate" skills={result.extra_skills} />
      </section>

      {result.suggestions.length > 0 && (
        <section className="card">
          <h3 className="section-title mb-3">Fix these first</h3>
          <ol className="space-y-2.5">
            {result.suggestions.map((suggestion, index) => (
              <li key={suggestion} className="flex gap-3 text-sm text-slate-300">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full
                                 bg-brand-500/15 text-xs font-bold text-brand-400">
                  {index + 1}
                </span>
                {suggestion}
              </li>
            ))}
          </ol>
          <Link to="/interview" className="btn-primary mt-5">
            Practise an interview for this role →
          </Link>
        </section>
      )}
    </>
  )
}

const TONES: Record<string, string> = {
  emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  rose: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
  amber: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  slate: 'border-ink-600 bg-ink-800 text-slate-400',
}

function SkillGroup({ title, tone, skills, note }: {
  title: string; tone: string; skills: string[]; note?: string
}) {
  if (skills.length === 0) return null
  return (
    <div className="mb-4 last:mb-0">
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title} ({skills.length})
      </div>
      <div className="flex flex-wrap gap-1.5">
        {skills.map((skill) => <Chip key={skill} className={TONES[tone]}>{skill}</Chip>)}
      </div>
      {note && <p className="mt-1.5 text-xs text-slate-500">{note}</p>}
    </div>
  )
}
