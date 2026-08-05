/** Small formatting helpers shared across pages. */

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-slate-400'
  if (score >= 80) return 'text-emerald-400'
  if (score >= 64) return 'text-lime-400'
  if (score >= 45) return 'text-amber-400'
  return 'text-rose-400'
}

export function scoreStroke(score: number): string {
  if (score >= 80) return '#34d399'
  if (score >= 64) return '#a3e635'
  if (score >= 45) return '#fbbf24'
  return '#fb7185'
}

export function scoreBg(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-slate-500/15 text-slate-300 border-slate-500/30'
  if (score >= 80) return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
  if (score >= 64) return 'bg-lime-500/15 text-lime-300 border-lime-500/30'
  if (score >= 45) return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
  return 'bg-rose-500/15 text-rose-300 border-rose-500/30'
}

export const CATEGORY_STYLES: Record<string, string> = {
  technical: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  behavioral: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  situational: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  resume: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  coding: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
}

export const PRIORITY_STYLES: Record<string, string> = {
  critical: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  high: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  medium: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  low: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
}

export const KIND_ICON: Record<string, string> = {
  course: '🎓',
  reading: '📖',
  practice: '⌨️',
  project: '🛠️',
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 1) return '—'
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function titleCase(value: string): string {
  return value.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function clockFrom(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
