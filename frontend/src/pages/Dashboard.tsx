import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { DashboardStats } from '../lib/types'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { EmptyState, PageHeader, ScoreChip, Spinner, StatCard, TrendChart } from '../components/ui'
import { formatDateTime, titleCase } from '../lib/format'

export default function Dashboard() {
  const { user } = useAuth()
  const toast = useToast()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.dashboard()
      .then(setStats)
      .catch((error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [toast])

  if (loading) return <Spinner label="Loading your dashboard…" />
  if (!stats) return null

  const firstName = (user?.full_name || user?.email || '').split(/[ @]/)[0]
  const brandNew = stats.resumes === 0 && stats.interviews_started === 0

  return (
    <>
      <PageHeader
        title={`Hello${firstName ? `, ${firstName}` : ''} 👋`}
        subtitle={brandNew
          ? 'Start by uploading your resume — everything else builds on it.'
          : `Preparing for ${titleCase(user?.target_role ?? '')} roles.`}
        action={<Link to="/interview" className="btn-primary">Start a mock interview</Link>}
      />

      {brandNew ? (
        <EmptyState
          icon="📄"
          title="Upload your resume to begin"
          body="We parse it, score it the way an ATS would, and use it to ask you interview
                questions about your own projects."
          action={<Link to="/resume" className="btn-primary">Upload resume</Link>}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="ATS score" value={stats.latest_ats_score ?? '—'} tone="score"
                      hint={stats.best_ats_score !== null ? `Best: ${stats.best_ats_score}` : 'Analyse a resume'} />
            <StatCard label="Interview average" value={stats.average_interview_score ?? '—'} tone="score"
                      hint={stats.best_interview_score !== null ? `Best: ${stats.best_interview_score}` : 'No interviews yet'} />
            <StatCard label="Questions answered" value={stats.questions_answered}
                      hint={`${stats.interviews_completed} interviews completed`} />
            <StatCard label="Practice time" value={`${stats.practice_minutes}m`}
                      hint="Total time spoken" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <section className="card lg:col-span-2">
              <h2 className="section-title mb-1">Score trend</h2>
              <p className="muted mb-2">Your last {stats.score_trend.length} completed interviews.</p>
              <TrendChart points={stats.score_trend} />
            </section>

            <section className="card">
              <h2 className="section-title mb-3">What to work on</h2>
              {stats.weakest_dimension ? (
                <>
                  <p className="text-sm text-slate-300">
                    Your weakest dimension is{' '}
                    <strong className="text-rose-300">{stats.weakest_dimension}</strong>
                    {stats.strongest_dimension && (
                      <> and your strongest is{' '}
                        <strong className="text-emerald-300">{stats.strongest_dimension}</strong></>
                    )}.
                  </p>
                  <Link to="/roadmap" className="btn-primary mt-4 w-full">
                    {stats.has_roadmap ? 'Open your roadmap' : 'Build my roadmap'}
                  </Link>
                </>
              ) : (
                <>
                  <p className="text-sm text-slate-400">
                    Finish one mock interview and this becomes a specific, ranked list of
                    what is costing you offers.
                  </p>
                  <Link to="/interview" className="btn-primary mt-4 w-full">Take an interview</Link>
                </>
              )}

              {stats.latest_resume && (
                <div className="mt-5 border-t border-ink-700 pt-4">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Current resume</div>
                  <div className="mt-1 truncate text-sm text-slate-200">
                    {stats.latest_resume.filename}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {stats.latest_resume.skills.length} skills detected
                  </div>
                  <Link to="/resume" className="btn-ghost mt-3 w-full">Manage resumes</Link>
                </div>
              )}
            </section>
          </div>

          <section className="card mt-6">
            <h2 className="section-title mb-3">Recent interviews</h2>
            {stats.recent_interviews.length === 0 ? (
              <p className="muted">No interviews yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="pb-2 pr-4">Date</th>
                      <th className="pb-2 pr-4">Role</th>
                      <th className="pb-2 pr-4">Mode</th>
                      <th className="pb-2 pr-4">Status</th>
                      <th className="pb-2 pr-4">Score</th>
                      <th className="pb-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-700/70">
                    {stats.recent_interviews.map((interview) => (
                      <tr key={interview.id}>
                        <td className="py-2.5 pr-4 text-slate-400">
                          {formatDateTime(interview.started_at)}
                        </td>
                        <td className="py-2.5 pr-4">{titleCase(interview.role_key)}</td>
                        <td className="py-2.5 pr-4 text-slate-400">{interview.mode}</td>
                        <td className="py-2.5 pr-4">
                          <span className={`chip ${interview.status === 'completed'
                            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                            : 'border-amber-500/30 bg-amber-500/10 text-amber-300'}`}>
                            {interview.status.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4"><ScoreChip score={interview.overall_score} /></td>
                        <td className="py-2.5 text-right">
                          <Link
                            to={interview.status === 'completed'
                              ? `/report/${interview.id}` : `/interview/${interview.id}`}
                            className="text-sm font-medium text-brand-400 hover:underline">
                            {interview.status === 'completed' ? 'View report' : 'Resume'}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  )
}
