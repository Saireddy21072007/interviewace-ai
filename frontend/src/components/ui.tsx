/** Small presentational building blocks shared by every page. */

import type { ReactNode } from 'react'
import { scoreBg, scoreColor, scoreStroke } from '../lib/format'

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-10 text-slate-400">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-ink-600 border-t-brand-500" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}

export function PageHeader({ title, subtitle, action }: {
  title: string; subtitle?: string; action?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-slate-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function EmptyState({ icon, title, body, action }: {
  icon: string; title: string; body: string; action?: ReactNode
}) {
  return (
    <div className="card flex flex-col items-center gap-3 py-12 text-center">
      <div className="text-4xl">{icon}</div>
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      <p className="max-w-md text-sm text-slate-400">{body}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function StatCard({ label, value, hint, tone = 'default' }: {
  label: string; value: ReactNode; hint?: string; tone?: 'default' | 'score'
}) {
  const numeric = typeof value === 'number' ? value : null
  return (
    <div className="card">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1.5 text-3xl font-bold ${
        tone === 'score' && numeric !== null ? scoreColor(numeric) : 'text-white'}`}>
        {value ?? '—'}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

/** Circular score gauge. `max` lets it render 0-10 rubric scores too. */
export function ScoreRing({ score, max = 100, size = 132, label }: {
  score: number; max?: number; size?: number; label?: string
}) {
  const normalised = Math.max(0, Math.min(100, (score / max) * 100))
  const radius = size / 2 - 10
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (normalised / 100) * circumference

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
                stroke="rgba(148,163,184,0.14)" strokeWidth={9} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke={scoreStroke(normalised)} strokeWidth={9} strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 700ms ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-bold ${scoreColor(normalised)}`}>{Math.round(score)}</span>
        <span className="text-[11px] uppercase tracking-wide text-slate-500">
          {label ?? `of ${max}`}
        </span>
      </div>
    </div>
  )
}

export function ScoreBar({ label, score, max = 10, detail }: {
  label: string; score: number; max?: number; detail?: string
}) {
  const percent = Math.max(0, Math.min(100, (score / max) * 100))
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        <span className={`text-sm font-semibold ${scoreColor(percent)}`}>
          {score}<span className="text-slate-500">/{max}</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-ink-700">
        <div className="h-full rounded-full transition-all duration-700"
             style={{ width: `${percent}%`, backgroundColor: scoreStroke(percent) }} />
      </div>
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </div>
  )
}

export function Chip({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`chip ${className}`}>{children}</span>
}

export function ScoreChip({ score }: { score: number | null | undefined }) {
  return <span className={`chip ${scoreBg(score)}`}>{score ?? '—'}</span>
}

/** Hand-rolled sparkline. A charting library would be ~90KB for one graph. */
export function TrendChart({ points }: { points: { date: string; score: number }[] }) {
  if (points.length < 2) {
    return (
      <p className="py-8 text-center text-sm text-slate-500">
        Take at least two interviews to see your progress over time.
      </p>
    )
  }

  const width = 560
  const height = 160
  const padding = 24
  const scores = points.map((p) => p.score)
  const min = Math.max(0, Math.min(...scores) - 8)
  const max = Math.min(100, Math.max(...scores) + 8)
  const span = max - min || 1

  const coords = points.map((point, index) => ({
    x: padding + (index * (width - padding * 2)) / (points.length - 1),
    y: height - padding - ((point.score - min) / span) * (height - padding * 2),
    score: point.score,
    date: point.date,
  }))

  const line = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ')
  const area = `${line} L ${coords[coords.length - 1].x} ${height - padding} L ${coords[0].x} ${height - padding} Z`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img"
         aria-label="Interview score trend">
      <defs>
        <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#5b6cff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#5b6cff" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((fraction) => (
        <line key={fraction} x1={padding} x2={width - padding}
              y1={padding + fraction * (height - padding * 2)}
              y2={padding + fraction * (height - padding * 2)}
              stroke="rgba(148,163,184,0.12)" strokeWidth={1} />
      ))}
      <path d={area} fill="url(#trendFill)" />
      <path d={line} fill="none" stroke="#7c8cff" strokeWidth={2.5} strokeLinecap="round" />
      {coords.map((coord) => (
        <g key={`${coord.date}-${coord.x}`}>
          <circle cx={coord.x} cy={coord.y} r={4} fill="#0d1220" stroke="#7c8cff" strokeWidth={2} />
          <text x={coord.x} y={coord.y - 12} textAnchor="middle"
                className="fill-slate-400 text-[11px]">{coord.score}</text>
        </g>
      ))}
    </svg>
  )
}
