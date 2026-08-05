import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { Interview, Report, ReportQuestion } from '../lib/types'
import { useToast } from '../context/ToastContext'
import { Chip, EmptyState, PageHeader, ScoreBar, ScoreRing, Spinner } from '../components/ui'
import { CATEGORY_STYLES, formatDateTime, formatDuration, scoreColor, titleCase } from '../lib/format'

/** Module 8: the interview report. */
export default function ReportPage() {
  const { interviewId } = useParams<{ interviewId?: string }>()
  const toast = useToast()
  const [report, setReport] = useState<Report | null>(null)
  const [history, setHistory] = useState<Interview[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(1)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.report(interviewId ? Number(interviewId) : undefined),
      api.interviews(),
    ])
      .then(([reportData, interviews]) => {
        setReport(reportData)
        setHistory(interviews.filter((item) => item.status === 'completed'))
        setMissing(false)
      })
      .catch((error) => {
        if (error.status === 404) setMissing(true)
        else toast.error(error.message)
      })
      .finally(() => setLoading(false))
  }, [interviewId, toast])

  if (loading) return <Spinner label="Loading your report…" />

  if (missing || !report) {
    return (
      <EmptyState
        icon="📈"
        title="No report yet"
        body="Finish a mock interview and this page fills with a score for every answer,
              what a strong answer would have contained, and what to practise."
        action={<Link to="/interview" className="btn-primary">Take an interview</Link>}
      />
    )
  }

  const dimensions = Object.entries(report.dimension_averages ?? {})

  return (
    <>
      <PageHeader
        title="Interview report"
        subtitle={`${titleCase(report.interview.role_key)} · ${
          formatDateTime(report.interview.completed_at ?? report.interview.started_at)}`}
        action={<Link to="/interview" className="btn-primary">New interview</Link>}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
        <div className="space-y-6">
          <section className="card text-center">
            <ScoreRing score={report.overall_score} size={150} />
            <p className={`mt-3 font-semibold ${scoreColor(report.overall_score)}`}>
              {report.verdict}
            </p>
            <p className="mt-1 text-sm text-slate-400">
              {report.answered} of {report.total} questions answered
            </p>
            {report.headline && (
              <p className="mt-3 rounded-xl border border-ink-700 bg-ink-800/50 px-3.5 py-2.5 text-left text-sm text-slate-300">
                {report.headline}
              </p>
            )}
          </section>

          {dimensions.length > 0 && (
            <section className="card">
              <h2 className="section-title mb-1">The five dimensions</h2>
              <p className="muted mb-4">Averaged across every answer you gave.</p>
              <div className="space-y-4">
                {dimensions.map(([name, score]) => (
                  <ScoreBar key={name} label={titleCase(name)} score={score as number} max={10} />
                ))}
              </div>
            </section>
          )}

          {Object.keys(report.by_category).length > 0 && (
            <section className="card">
              <h2 className="section-title mb-3">By question type</h2>
              <div className="space-y-3">
                {Object.entries(report.by_category).map(([category, score]) => (
                  <ScoreBar key={category} label={titleCase(category)} score={score} max={100} />
                ))}
              </div>
            </section>
          )}

          {history.length > 1 && (
            <section className="card">
              <h2 className="section-title mb-3">Past interviews</h2>
              <ul className="space-y-1.5">
                {history.map((item) => (
                  <li key={item.id}>
                    <Link to={`/report/${item.id}`}
                          className={`flex items-center justify-between rounded-lg px-2.5 py-2 text-sm transition ${
                            item.id === report.interview.id
                              ? 'bg-brand-500/15 text-brand-400'
                              : 'text-slate-400 hover:bg-ink-800'}`}>
                      <span>{formatDateTime(item.completed_at)}</span>
                      <span className={`font-semibold ${scoreColor(item.overall_score)}`}>
                        {item.overall_score}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className="space-y-6">
          {(report.strengths.length > 0 || report.improvements.length > 0) && (
            <div className="grid gap-4 sm:grid-cols-2">
              <section className="card">
                <h2 className="mb-3 font-semibold text-emerald-300">What went well</h2>
                <ul className="space-y-2 text-sm text-slate-300">
                  {report.strengths.length === 0 && <li className="text-slate-500">—</li>}
                  {report.strengths.map((item) => (
                    <li key={item} className="flex gap-2"><span className="text-emerald-400">✓</span>{item}</li>
                  ))}
                </ul>
              </section>
              <section className="card">
                <h2 className="mb-3 font-semibold text-amber-300">What to fix</h2>
                <ul className="space-y-2 text-sm text-slate-300">
                  {report.improvements.length === 0 && <li className="text-slate-500">—</li>}
                  {report.improvements.map((item) => (
                    <li key={item} className="flex gap-2"><span className="text-amber-400">→</span>{item}</li>
                  ))}
                </ul>
              </section>
            </div>
          )}

          <section>
            <h2 className="section-title mb-3">Answer by answer</h2>
            <div className="space-y-3">
              {report.questions.map((item) => (
                <QuestionCard key={item.index} item={item}
                              open={expanded === item.index}
                              onToggle={() => setExpanded(expanded === item.index ? null : item.index)} />
              ))}
            </div>
          </section>

          <div className="flex flex-wrap gap-3">
            <Link to="/roadmap" className="btn-primary">Turn this into a study plan →</Link>
            <Link to="/interview" className="btn-ghost">Practise again</Link>
          </div>
        </div>
      </div>
    </>
  )
}

function QuestionCard({ item, open, onToggle }: {
  item: ReportQuestion; open: boolean; onToggle: () => void
}) {
  const evaluation = item.evaluation ?? {}
  const metrics = evaluation.metrics

  return (
    <article className="card !p-0 overflow-hidden">
      <button onClick={onToggle} className="flex w-full items-start gap-3 p-4 text-left">
        <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${
          item.overall_score === null ? 'bg-ink-700 text-slate-400'
            : item.overall_score >= 70 ? 'bg-emerald-500/20 text-emerald-300'
            : item.overall_score >= 45 ? 'bg-amber-500/20 text-amber-300'
            : 'bg-rose-500/20 text-rose-300'}`}>
          {item.overall_score ?? '–'}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            <Chip className={CATEGORY_STYLES[item.category] ?? CATEGORY_STYLES.technical}>
              {item.category}
            </Chip>
            {item.skill && (
              <Chip className="border-ink-600 bg-ink-800 text-slate-400">{item.skill}</Chip>
            )}
            {item.duration_sec != null && (
              <span className="text-xs text-slate-500">{formatDuration(item.duration_sec)}</span>
            )}
          </div>
          <p className="text-sm font-medium text-slate-100">
            Q{item.index}. {item.question}
          </p>
        </div>
        <span className="mt-1 text-slate-500">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-ink-700/70 p-4 pt-4">
          <div>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {item.code ? 'Your code' : 'What you said'}
            </h4>
            {item.code ? (
              <pre className="overflow-x-auto rounded-xl bg-ink-950/70 p-3.5 font-mono text-xs text-slate-300">
                {item.code}
              </pre>
            ) : (
              <p className="rounded-xl bg-ink-950/50 p-3.5 text-sm leading-relaxed text-slate-300">
                {item.transcript || <span className="text-slate-500">No answer given.</span>}
              </p>
            )}
            {metrics && (
              <p className="mt-1.5 text-xs text-slate-500">
                {metrics.word_count} words
                {metrics.words_per_minute ? ` · ${metrics.words_per_minute} wpm (${metrics.pace})` : ''}
                {metrics.filler_count ? ` · ${metrics.filler_count} fillers` : ''}
                {metrics.quantified_claims ? ` · ${metrics.quantified_claims} numbers used` : ''}
              </p>
            )}
          </div>

          {evaluation.scores && (
            <div className="grid gap-3 sm:grid-cols-2">
              {Object.entries(evaluation.scores).map(([name, score]) => (
                <ScoreBar key={name} label={titleCase(name)} score={score as number} max={10}
                          detail={evaluation.reasons?.[name]} />
              ))}
            </div>
          )}

          {evaluation.static_checks && (
            <ul className="space-y-1.5">
              {evaluation.static_checks.map((check) => (
                <li key={check.name} className="flex gap-2 text-sm">
                  <span className={check.passed ? 'text-emerald-400' : 'text-rose-400'}>
                    {check.passed ? '✓' : '✕'}
                  </span>
                  <span className="text-slate-300">{check.detail}</span>
                </li>
              ))}
            </ul>
          )}

          {item.expected_points.length > 0 && (
            <div>
              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                What a strong answer contains
              </h4>
              <ul className="space-y-1">
                {item.expected_points.map((point) => {
                  const covered = evaluation.covered_points?.includes(point)
                  return (
                    <li key={point} className="flex gap-2 text-sm">
                      <span className={covered ? 'text-emerald-400' : 'text-slate-600'}>
                        {covered ? '✓' : '○'}
                      </span>
                      <span className={covered ? 'text-slate-300' : 'text-slate-400'}>{point}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {(evaluation.strengths?.length || evaluation.improvements?.length) && (
            <div className="grid gap-3 sm:grid-cols-2">
              {evaluation.strengths && evaluation.strengths.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-400">
                    Strengths
                  </h4>
                  <ul className="space-y-1 text-sm text-slate-300">
                    {evaluation.strengths.map((s) => <li key={s}>✓ {s}</li>)}
                  </ul>
                </div>
              )}
              {evaluation.improvements && evaluation.improvements.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-amber-400">
                    Improve
                  </h4>
                  <ul className="space-y-1 text-sm text-slate-300">
                    {evaluation.improvements.map((s) => <li key={s}>→ {s}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}

          {evaluation.model_answer && (
            <div>
              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-brand-400">
                Model answer
              </h4>
              <p className="rounded-xl border border-brand-500/25 bg-brand-500/5 p-3.5 text-sm
                            leading-relaxed text-slate-300">
                {evaluation.model_answer}
              </p>
            </div>
          )}

          {evaluation.note && <p className="text-xs text-slate-500">{evaluation.note}</p>}
        </div>
      )}
    </article>
  )
}
