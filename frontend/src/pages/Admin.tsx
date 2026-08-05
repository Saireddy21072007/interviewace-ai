import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { AdminStats, AdminUserRow } from '../lib/types'
import { useToast } from '../context/ToastContext'
import { Chip, PageHeader, Spinner, StatCard } from '../components/ui'
import { formatDateTime } from '../lib/format'

/**
 * Module 10: admin dashboard.
 *
 * Two jobs: platform numbers, and whether the AI engines are actually live.
 * The warnings panel is the important half — it is what stops a demo running
 * on fallbacks while everyone assumes the model is answering.
 */
export default function Admin() {
  const toast = useToast()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.adminStats(), api.adminUsers()])
      .then(([statsData, userList]) => { setStats(statsData); setUsers(userList) })
      .catch((error) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [toast])

  async function toggleActive(user: AdminUserRow) {
    try {
      const updated = await api.adminSetActive(user.id, !user.is_active)
      setUsers((current) => current.map((row) => (row.id === updated.id ? { ...row, ...updated } : row)))
      toast.success(`${updated.email} ${updated.is_active ? 'enabled' : 'disabled'}.`)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  if (loading) return <Spinner label="Loading platform stats…" />
  if (!stats) return null

  return (
    <>
      <PageHeader title="Admin console"
                  subtitle="Platform usage and the health of the AI engines behind it." />

      {stats.warnings.length > 0 && (
        <div className="mb-6 space-y-2">
          {stats.warnings.map((warning) => (
            <div key={warning}
                 className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              ⚠ {warning}
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Users" value={stats.users} hint={`${stats.active_users_7d} active in 7 days`} />
        <StatCard label="Resumes" value={stats.resumes}
                  hint={stats.average_ats_score !== null ? `Avg ATS ${stats.average_ats_score}` : '—'} />
        <StatCard label="Interviews" value={stats.interviews}
                  hint={`${stats.completed_interviews} completed`} />
        <StatCard label="Answers scored" value={stats.answers}
                  hint={stats.average_interview_score !== null
                    ? `Avg score ${stats.average_interview_score}` : '—'} />
      </div>

      <section className="card mt-6">
        <h2 className="section-title mb-3">System</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Engine title="Language model"
                  live={stats.llm.available}
                  value={stats.llm.available ? `${stats.llm.provider} · ${stats.llm.model}` : 'offline engine'}
                  note={stats.llm.available
                    ? 'Questions and feedback are model-generated.'
                    : 'Using the built-in question bank and heuristic scorer.'} />
          <Engine title="Speech to text"
                  live={stats.stt.effective !== 'none'}
                  value={stats.stt.effective}
                  note={stats.stt.effective === 'none'
                    ? 'Falling back to the browser Web Speech API.'
                    : 'Server-side transcription is available.'} />
          <Engine title="Database" live value={stats.database}
                  note={stats.database === 'sqlite'
                    ? 'Fine for development. Switch DATABASE_URL to PostgreSQL for production.'
                    : 'PostgreSQL connected.'} />
        </div>
      </section>

      <section className="card mt-6">
        <h2 className="section-title mb-3">Users</h2>
        <p className="muted mb-4">
          Admins see accounts and usage only. Resume text, transcripts and audio stay private
          to the candidate.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="pb-2 pr-4">User</th>
                <th className="pb-2 pr-4">Role</th>
                <th className="pb-2 pr-4">Target</th>
                <th className="pb-2 pr-4">Resumes</th>
                <th className="pb-2 pr-4">Interviews</th>
                <th className="pb-2 pr-4">Last seen</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-700/70">
              {users.map((user) => (
                <tr key={user.id} className={user.is_active ? '' : 'opacity-50'}>
                  <td className="py-2.5 pr-4">
                    <div className="font-medium text-slate-100">{user.full_name || '—'}</div>
                    <div className="text-xs text-slate-500">{user.email}</div>
                  </td>
                  <td className="py-2.5 pr-4">
                    <Chip className={user.role === 'admin'
                      ? 'border-brand-500/30 bg-brand-500/10 text-brand-400'
                      : 'border-ink-600 bg-ink-800 text-slate-400'}>
                      {user.role}
                    </Chip>
                  </td>
                  <td className="py-2.5 pr-4 text-slate-400">{user.target_role}</td>
                  <td className="py-2.5 pr-4">{user.resume_count}</td>
                  <td className="py-2.5 pr-4">{user.interview_count}</td>
                  <td className="py-2.5 pr-4 text-slate-400">{formatDateTime(user.last_login_at)}</td>
                  <td className="py-2.5 text-right">
                    <button className="text-sm font-medium text-brand-400 hover:underline"
                            onClick={() => toggleActive(user)}>
                      {user.is_active ? 'Disable' : 'Enable'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function Engine({ title, live, value, note }: {
  title: string; live: boolean; value: string; note: string
}) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-800/40 p-4">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${live ? 'bg-emerald-400' : 'bg-amber-400'}`} />
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</span>
      </div>
      <div className="mt-1.5 font-medium text-slate-100">{value}</div>
      <p className="mt-1 text-xs text-slate-500">{note}</p>
    </div>
  )
}
