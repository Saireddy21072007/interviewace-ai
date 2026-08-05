import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ApiError, api } from '../lib/api'
import type { Role } from '../lib/types'
import { AuthShell } from './Login'

export default function Register() {
  const { register } = useAuth()
  const [roles, setRoles] = useState<Role[]>([])
  const [form, setForm] = useState({
    full_name: '', email: '', password: '',
    target_role: 'full-stack-developer', experience_level: 'fresher',
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.roles().then((data) => setRoles(data.roles)).catch(() => undefined) }, [])

  const rules = [
    { ok: form.password.length >= 8, text: 'at least 8 characters' },
    { ok: /[a-zA-Z]/.test(form.password), text: 'a letter' },
    { ok: /\d/.test(form.password), text: 'a number' },
  ]

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await register({ ...form, email: form.email.trim() })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Two minutes to set up. Everything runs locally by default."
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-brand-400 hover:underline">Sign in</Link></>}
    >
      <form onSubmit={onSubmit} className="space-y-4">
        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-200">
            {error}
          </div>
        )}

        <div>
          <label className="label" htmlFor="name">Full name</label>
          <input id="name" className="input" placeholder="Ananya Sharma" value={form.full_name}
                 onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </div>

        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="email" className="input"
                 placeholder="you@example.com" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>

        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" required autoComplete="new-password" className="input"
                 placeholder="••••••••" value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <div className="mt-2 flex flex-wrap gap-2">
            {rules.map((rule) => (
              <span key={rule.text}
                    className={`chip ${rule.ok
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : 'border-ink-600 bg-ink-800 text-slate-500'}`}>
                {rule.ok ? '✓' : '○'} {rule.text}
              </span>
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="role">Target role</label>
            <select id="role" className="input" value={form.target_role}
                    onChange={(e) => setForm({ ...form, target_role: e.target.value })}>
              {roles.length === 0 && <option value="full-stack-developer">Full Stack Developer</option>}
              {roles.map((role) => <option key={role.key} value={role.key}>{role.title}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="level">Experience</label>
            <select id="level" className="input" value={form.experience_level}
                    onChange={(e) => setForm({ ...form, experience_level: e.target.value })}>
              <option value="fresher">Fresher / student</option>
              <option value="junior">0-2 years</option>
              <option value="mid">2-5 years</option>
              <option value="senior">5+ years</option>
            </select>
          </div>
        </div>

        <button type="submit" className="btn-primary w-full"
                disabled={busy || rules.some((rule) => !rule.ok)}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  )
}
