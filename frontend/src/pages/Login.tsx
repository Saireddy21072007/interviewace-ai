import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../lib/api'

export default function Login() {
  const { login } = useAuth()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(
    params.get('expired') ? 'Your session expired. Please sign in again.' : null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to keep practising."
      footer={<>New here? <Link to="/register" className="font-semibold text-brand-400 hover:underline">Create an account</Link></>}
    >
      <form onSubmit={onSubmit} className="space-y-4">
        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-200">
            {error}
          </div>
        )}
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="email" className="input"
                 placeholder="you@example.com"
                 value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" required autoComplete="current-password"
                 className="input" placeholder="••••••••"
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthShell>
  )
}

export function AuthShell({ title, subtitle, children, footer }: {
  title: string; subtitle: string; children: React.ReactNode; footer: React.ReactNode
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 text-xl font-bold text-white">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500/20">🎯</span>
            InterviewAce<span className="text-brand-400">AI</span>
          </div>
          <h1 className="text-2xl font-bold text-white">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-slate-400">{subtitle}</p>
          {children}
          <p className="mt-6 text-sm text-slate-400">{footer}</p>
        </div>
      </div>

      <aside className="relative hidden overflow-hidden border-l border-ink-700/60 lg:block">
        <div className="absolute inset-0 bg-gradient-to-br from-brand-600/20 via-ink-950 to-cyan-500/10" />
        <div className="relative flex h-full flex-col justify-center gap-6 px-14">
          <h2 className="text-3xl font-bold leading-tight text-white">
            Practise the interview<br />before it counts.
          </h2>
          <ul className="space-y-4 text-slate-300">
            {[
              ['📄', 'ATS resume score', 'See the number a recruiter’s software sees, and exactly which rule cost you each point.'],
              ['🎙️', 'Voice mock interviews', 'Questions asked out loud, answered out loud, transcribed as you speak.'],
              ['📊', 'Scored on five dimensions', 'Relevance, depth, structure, specificity and clarity — so you know what to fix.'],
              ['🗺️', 'A plan that fits your week', 'Your gaps, packed into the hours you actually have.'],
            ].map(([icon, heading, body]) => (
              <li key={heading} className="flex gap-3">
                <span className="text-xl">{icon}</span>
                <div>
                  <div className="font-semibold text-white">{heading}</div>
                  <div className="text-sm text-slate-400">{body}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  )
}
