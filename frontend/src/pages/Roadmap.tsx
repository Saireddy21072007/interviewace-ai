import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Roadmap } from '../lib/types'
import { useToast } from '../context/ToastContext'
import { Chip, EmptyState, PageHeader, Spinner } from '../components/ui'
import { KIND_ICON, PRIORITY_STYLES, titleCase } from '../lib/format'

/** Module 9: the personalised learning roadmap. */
export default function RoadmapPage() {
  const toast = useToast()
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null)
  const [loading, setLoading] = useState(true)
  const [blocked, setBlocked] = useState<string | null>(null)
  const [weeks, setWeeks] = useState(8)
  const [hours, setHours] = useState(8)
  const [rebuilding, setRebuilding] = useState(false)

  useEffect(() => {
    api.roadmap()
      .then((data) => {
        setRoadmap(data)
        setWeeks(data.week_count)
        setHours(data.hours_per_week)
      })
      .catch((error) => {
        if (error.status === 409 || error.status === 404) setBlocked(error.message)
        else toast.error(error.message)
      })
      .finally(() => setLoading(false))
  }, [toast])

  async function rebuild() {
    setRebuilding(true)
    try {
      const data = await api.createRoadmap({ weeks, hours_per_week: hours })
      setRoadmap(data)
      setBlocked(null)
      toast.success(`Rebuilt: ${data.total_hours} hours across ${data.week_count} weeks.`)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setRebuilding(false)
    }
  }

  async function toggle(weekNumber: number, taskIndex: number, done: boolean) {
    if (!roadmap) return
    const key = `${weekNumber}-${taskIndex}`
    // Optimistic: ticking a checkbox should never wait on a round trip.
    setRoadmap({ ...roadmap, progress: { ...roadmap.progress, [key]: done } })
    try {
      const updated = await api.setTaskDone(roadmap.id, key, done)
      setRoadmap(updated)
    } catch (error) {
      toast.error((error as Error).message)
      setRoadmap(roadmap)
    }
  }

  if (loading) return <Spinner label="Building your roadmap…" />

  if (blocked || !roadmap) {
    return (
      <EmptyState
        icon="🗺️"
        title="Analyse a resume first"
        body={blocked ?? 'Your roadmap is built from the gap between your resume and the role you are targeting, so we need an analysed resume to start from.'}
        action={<Link to="/resume" className="btn-primary">Go to resume analyzer</Link>}
      />
    )
  }

  const allTasks = roadmap.weeks.flatMap((week) =>
    week.tasks.map((task, index) => ({ key: `${week.week}-${index}`, task })))
  const doneCount = allTasks.filter((entry) => roadmap.progress[entry.key]).length
  const percent = allTasks.length ? Math.round((doneCount / allTasks.length) * 100) : 0

  return (
    <>
      <PageHeader
        title="Your learning roadmap"
        subtitle={`${titleCase(roadmap.role_key)} · ${roadmap.total_hours} hours across
                   ${roadmap.week_count} weeks, packed into ${roadmap.hours_per_week} hours a week.`}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,300px)]">
        <div className="space-y-5">
          {roadmap.coach_note && (
            <section className="card border-brand-500/25 bg-brand-500/5">
              <div className="flex gap-3">
                <span className="text-2xl">🧭</span>
                <p className="text-sm leading-relaxed text-slate-200">{roadmap.coach_note}</p>
              </div>
            </section>
          )}

          {roadmap.weeks.map((week) => (
            <section key={week.week} className="card">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-500/15
                                 text-sm font-bold text-brand-400">
                  W{week.week}
                </span>
                <div>
                  <h2 className="font-semibold text-white">{week.theme}</h2>
                  <p className="text-xs text-slate-500">{week.hours} hours planned</p>
                </div>
              </div>

              <ul className="space-y-2">
                {week.tasks.map((task, index) => {
                  const key = `${week.week}-${index}`
                  const done = !!roadmap.progress[key]
                  return (
                    <li key={key}
                        className={`flex items-start gap-3 rounded-xl border px-3.5 py-3 transition ${
                          done ? 'border-emerald-500/25 bg-emerald-500/5'
                               : 'border-ink-700 bg-ink-800/40'}`}>
                      <input type="checkbox" checked={done} className="mt-1 h-4 w-4 accent-brand-500"
                             onChange={(e) => toggle(week.week, index, e.target.checked)} />
                      <div className="min-w-0 flex-1">
                        <div className={`text-sm font-medium ${
                          done ? 'text-slate-500 line-through' : 'text-slate-100'}`}>
                          {KIND_ICON[task.kind] ?? '•'} {task.url ? (
                            <a href={task.url} target="_blank" rel="noreferrer"
                               className="hover:text-brand-400 hover:underline">{task.title} ↗</a>
                          ) : task.title}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          <Chip className={PRIORITY_STYLES[task.priority]}>{task.priority}</Chip>
                          <Chip className="border-ink-600 bg-ink-800 text-slate-400">
                            {task.skill}
                          </Chip>
                          <span className="text-xs text-slate-500">{task.hours}h</span>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>

              {week.outcome && (
                <p className="mt-3 rounded-xl border border-ink-700 bg-ink-950/40 px-3.5 py-2.5
                              text-sm text-slate-400">
                  🎯 {week.outcome}
                </p>
              )}
            </section>
          ))}
        </div>

        <aside className="space-y-5 lg:sticky lg:top-24 lg:h-fit">
          <section className="card">
            <h2 className="section-title mb-3">Progress</h2>
            <div className="mb-2 flex items-baseline justify-between">
              <span className="text-3xl font-bold text-white">{percent}%</span>
              <span className="text-sm text-slate-400">{doneCount}/{allTasks.length} tasks</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-ink-700">
              <div className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                   style={{ width: `${percent}%` }} />
            </div>
          </section>

          <section className="card">
            <h2 className="section-title mb-3">Rebuild the plan</h2>
            <div className="space-y-4">
              <div>
                <label className="label" htmlFor="weeks">Weeks until you apply: {weeks}</label>
                <input id="weeks" type="range" min={2} max={16} value={weeks}
                       className="w-full accent-brand-500"
                       onChange={(e) => setWeeks(Number(e.target.value))} />
              </div>
              <div>
                <label className="label" htmlFor="hours">Hours you can study a week: {hours}</label>
                <input id="hours" type="range" min={2} max={30} value={hours}
                       className="w-full accent-brand-500"
                       onChange={(e) => setHours(Number(e.target.value))} />
              </div>
              <button className="btn-primary w-full" onClick={rebuild} disabled={rebuilding}>
                {rebuilding ? 'Rebuilding…' : 'Rebuild roadmap'}
              </button>
              <p className="text-xs text-slate-500">
                Rebuilding creates a new plan and resets ticked tasks.
              </p>
            </div>
          </section>

          {roadmap.gaps.length > 0 && (
            <section className="card">
              <h2 className="section-title mb-3">Why these things</h2>
              <ul className="space-y-3">
                {roadmap.gaps.slice(0, 6).map((gap) => (
                  <li key={gap.skill}>
                    <div className="flex items-center gap-2">
                      <Chip className={PRIORITY_STYLES[gap.priority]}>{gap.priority}</Chip>
                      <span className="text-sm font-medium text-slate-200">{gap.skill}</span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-500">{gap.why}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </>
  )
}
