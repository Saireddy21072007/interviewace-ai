import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { Answer, Interview, Question } from '../lib/types'
import { useToast } from '../context/ToastContext'
import { useRecorder } from '../hooks/useRecorder'
import { useSpeech } from '../hooks/useSpeech'
import { Chip, Spinner } from '../components/ui'
import { CATEGORY_STYLES, clockFrom } from '../lib/format'

/**
 * Module 6/7: the interview itself.
 *
 * The flow is deliberately linear and hard to get lost in: one question on
 * screen, one answer, next. Three things run behind it:
 *
 *   - the question is read aloud (browser TTS) so it feels like an interview
 *     rather than a form;
 *   - the answer is recorded AND transcribed live;
 *   - answers already submitted are shown in the sidebar with their scores,
 *     so progress is visible without leaving the page.
 *
 * Reloading is safe: the interview and its answers are re-fetched from the
 * server, and a candidate whose browser crashes mid-round can pick up exactly
 * where they were.
 */
export default function InterviewRoom() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const recorder = useRecorder()
  const speech = useSpeech()

  const [interview, setInterview] = useState<Interview | null>(null)
  const [questions, setQuestions] = useState<Question[]>([])
  const [answers, setAnswers] = useState<Record<number, Answer>>({})
  const [current, setCurrent] = useState(0)
  const [typed, setTyped] = useState('')
  const [code, setCode] = useState('')
  const [typing, setTyping] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [loading, setLoading] = useState(true)
  const spokenFor = useRef<number | null>(null)

  const question = questions[current] ?? null
  const isCoding = question?.category === 'coding'
  const answered = Object.keys(answers).length

  // ---------------------------------------------------------------- load
  useEffect(() => {
    if (!interviewId) return
    api.interview(Number(interviewId))
      .then((data) => {
        setInterview(data.interview)
        setQuestions(data.questions)
        const map: Record<number, Answer> = {}
        data.answers.forEach((answer) => { map[answer.question_id] = answer })
        setAnswers(map)
        const firstUnanswered = data.questions.findIndex((q) => !map[q.id])
        setCurrent(firstUnanswered === -1 ? data.questions.length - 1 : firstUnanswered)
      })
      .catch((error) => {
        toast.error(error.message)
        navigate('/interview')
      })
      .finally(() => setLoading(false))
  }, [interviewId, navigate, toast])

  // Read each new question aloud exactly once.
  useEffect(() => {
    if (!question || spokenFor.current === question.id) return
    spokenFor.current = question.id
    setTyped(answers[question.id]?.transcript ?? '')
    setCode(answers[question.id]?.code || question.problem?.starter_code || '')
    // Honour the mode chosen at setup: a candidate who picked "Type" should not
    // land on a microphone. Coding questions are always typed.
    setTyping(question.category === 'coding' || interview?.mode === 'text')
    recorder.reset()
    if (question.category !== 'coding') speech.speak(question.text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question?.id])

  const goTo = useCallback((index: number) => {
    if (index < 0 || index >= questions.length) return
    speech.stop()
    setCurrent(index)
  }, [questions.length, speech])

  // ---------------------------------------------------------------- submit
  async function submitTyped() {
    if (!question) return
    const value = isCoding ? code : typed
    if (!value.trim()) {
      toast.error(isCoding ? 'Write some code first.' : 'Type an answer first.')
      return
    }
    setSubmitting(true)
    try {
      const response = await api.submitAnswer({
        question_id: question.id,
        transcript: isCoding ? '' : typed.trim(),
        code: isCoding ? code : '',
        language: isCoding ? 'python' : 'python',
        evaluate_now: true,
      })
      setAnswers((current) => ({ ...current, [question.id]: response.answer }))
      toast.success(`Scored ${response.answer.overall_score}/100.`)
      advance()
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function submitSpoken() {
    if (!question) return
    const { blob, transcript, duration } = await recorder.stop()
    speech.stop()

    if (!transcript.trim() && !blob) {
      toast.error('Nothing was recorded. Try again, or type your answer.')
      return
    }

    setSubmitting(true)
    try {
      const response = blob
        ? await api.submitAudioAnswer({
            question_id: question.id, audio: blob,
            browser_transcript: transcript, duration_sec: duration,
          })
        : await api.submitAnswer({
            question_id: question.id, transcript, duration_sec: duration,
          })

      setAnswers((current) => ({ ...current, [question.id]: response.answer }))
      if (response.transcription?.note) toast.push(response.transcription.note, 'info')
      toast.success(`Scored ${response.answer.overall_score}/100.`)
      advance()
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  function advance() {
    if (current < questions.length - 1) goTo(current + 1)
  }

  async function finish() {
    if (!interview) return
    setFinishing(true)
    speech.stop()
    if (recorder.recording) await recorder.stop()
    try {
      const response = await api.finaliseInterview(interview.id)
      toast.success(`Interview complete — ${response.summary.overall}/100.`)
      navigate(`/report/${interview.id}`)
    } catch (error) {
      toast.error((error as Error).message)
      setFinishing(false)
    }
  }

  const progress = useMemo(
    () => (questions.length ? (answered / questions.length) * 100 : 0),
    [answered, questions.length],
  )

  if (loading) return <Spinner label="Loading your interview…" />
  if (!question || !interview) return null

  const existing = answers[question.id]

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,300px)]">
      <div className="space-y-5">
        {/* ---------------- progress ---------------- */}
        <div>
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium text-slate-300">
              Question {current + 1} of {questions.length}
            </span>
            <span className="text-slate-500">{answered} answered</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
            <div className="h-full rounded-full bg-brand-500 transition-all duration-500"
                 style={{ width: `${progress}%` }} />
          </div>
        </div>

        {/* ---------------- question ---------------- */}
        <section className="card animate-fade-up">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Chip className={CATEGORY_STYLES[question.category] ?? CATEGORY_STYLES.technical}>
              {question.category}
            </Chip>
            <Chip className="border-ink-600 bg-ink-800 text-slate-400">{question.difficulty}</Chip>
            {question.skill && (
              <Chip className="border-ink-600 bg-ink-800 text-slate-400">{question.skill}</Chip>
            )}
            <span className="ml-auto text-xs text-slate-500">
              suggested {Math.round(question.time_limit_sec / 60)} min
            </span>
          </div>

          {isCoding && question.problem?.title && (
            <h2 className="mb-2 text-lg font-bold text-white">{question.problem.title}</h2>
          )}

          <p className="text-lg leading-relaxed text-slate-100">{question.text}</p>

          {isCoding && question.problem?.examples && (
            <div className="mt-4 space-y-2">
              {question.problem.examples.map((example) => (
                <div key={example.input}
                     className="rounded-xl bg-ink-950/70 p-3 font-mono text-xs text-slate-400">
                  <div><span className="text-slate-500">Input: </span>{example.input}</div>
                  <div><span className="text-slate-500">Output: </span>{example.output}</div>
                </div>
              ))}
            </div>
          )}

          {!isCoding && speech.supported && (
            <div className="mt-4 flex items-center gap-2">
              <button className="btn-ghost !px-3 !py-1.5 text-xs"
                      onClick={() => speech.speak(question.text)}>
                {speech.speaking ? '🔊 Reading…' : '🔊 Read again'}
              </button>
              <label className="flex items-center gap-2 text-xs text-slate-500">
                <input type="checkbox" checked={speech.enabled} className="accent-brand-500"
                       onChange={(e) => {
                         speech.setEnabled(e.target.checked)
                         if (!e.target.checked) speech.stop()
                       }} />
                Read questions aloud
              </label>
            </div>
          )}
        </section>

        {/* ---------------- answer ---------------- */}
        <section className="card">
          {isCoding ? (
            <>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="section-title">Your solution</h3>
                <Chip className="border-ink-600 bg-ink-800 text-slate-400">python</Chip>
              </div>
              <textarea
                value={code} onChange={(e) => setCode(e.target.value)} spellCheck={false}
                rows={14}
                className="input resize-y font-mono text-sm leading-relaxed"
                placeholder="# your solution"
              />
              <p className="mt-2 text-xs text-slate-500">
                Your code is reviewed, not executed — running untrusted code needs a real
                sandbox, so we read it instead and tell you what would break.
              </p>
            </>
          ) : typing ? (
            <>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="section-title">Type your answer</h3>
                <button className="text-xs font-medium text-brand-400 hover:underline"
                        onClick={() => setTyping(false)}>
                  Switch to voice
                </button>
              </div>
              <textarea value={typed} onChange={(e) => setTyped(e.target.value)} rows={8}
                        className="input resize-y"
                        placeholder="Answer as if you were speaking it out loud…" />
              <p className="mt-1 text-xs text-slate-500">{typed.split(/\s+/).filter(Boolean).length} words</p>
            </>
          ) : (
            <VoiceAnswer recorder={recorder} onSwitchToTyping={() => {
              setTyping(true)
              setTyped(recorder.transcript)
            }} />
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {!isCoding && !typing ? (
              recorder.recording ? (
                <button className="btn-primary" onClick={submitSpoken} disabled={submitting}>
                  {submitting ? 'Scoring…' : '⏹ Stop & submit'}
                </button>
              ) : (
                <button className="btn-primary" onClick={() => { speech.stop(); recorder.start() }}
                        disabled={submitting || !recorder.supported}>
                  🎙️ Start recording
                </button>
              )
            ) : (
              <button className="btn-primary" onClick={submitTyped} disabled={submitting}>
                {submitting ? 'Scoring…' : existing ? 'Resubmit answer' : 'Submit answer'}
              </button>
            )}

            <button className="btn-ghost" onClick={() => goTo(current - 1)} disabled={current === 0}>
              ← Previous
            </button>
            <button className="btn-ghost" onClick={() => goTo(current + 1)}
                    disabled={current >= questions.length - 1}>
              Skip →
            </button>

            <button className="btn-ghost ml-auto" onClick={finish}
                    disabled={finishing || answered === 0}>
              {finishing ? 'Building report…' : `Finish & see report (${answered}/${questions.length})`}
            </button>
          </div>

          {recorder.error && (
            <p className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-200">
              {recorder.error}
            </p>
          )}
        </section>

        {/* ---------------- instant feedback ---------------- */}
        {existing?.evaluation && (
          <section className="card animate-fade-up">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="section-title">Feedback</h3>
              <Chip className="border-brand-500/30 bg-brand-500/10 text-brand-400">
                {existing.overall_score}/100
              </Chip>
              <span className="ml-auto text-xs text-slate-500">
                {existing.evaluation.source === 'llm' ? 'model-scored' : 'rule-scored'}
              </span>
            </div>
            {existing.evaluation.strengths?.map((item) => (
              <p key={item} className="text-sm text-emerald-300">✓ {item}</p>
            ))}
            {existing.evaluation.improvements?.map((item) => (
              <p key={item} className="text-sm text-amber-300">→ {item}</p>
            ))}
          </section>
        )}
      </div>

      {/* ---------------- sidebar ---------------- */}
      <aside className="lg:sticky lg:top-24 lg:h-fit">
        <section className="card">
          <h3 className="section-title mb-3">Questions</h3>
          <ol className="space-y-1.5">
            {questions.map((item, index) => {
              const answer = answers[item.id]
              return (
                <li key={item.id}>
                  <button onClick={() => goTo(index)}
                          className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition ${
                            index === current ? 'bg-brand-500/15 text-brand-400'
                                              : 'text-slate-400 hover:bg-ink-800'}`}>
                    <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                      answer ? 'bg-emerald-500/20 text-emerald-300' : 'bg-ink-700 text-slate-400'}`}>
                      {answer ? '✓' : index + 1}
                    </span>
                    <span className="line-clamp-1 flex-1">{item.text}</span>
                    {answer?.overall_score != null && (
                      <span className="text-xs font-semibold text-slate-400">
                        {answer.overall_score}
                      </span>
                    )}
                  </button>
                </li>
              )
            })}
          </ol>
        </section>

        <section className="card mt-4">
          <h3 className="mb-2 text-sm font-semibold text-white">Answering well</h3>
          <ul className="space-y-1.5 text-xs text-slate-400">
            <li>• Aim for 90–180 seconds. Longer and the interviewer stops listening.</li>
            <li>• Behavioural questions: Situation, Task, Action, <strong>Result</strong>.</li>
            <li>• Put a number in it. "Cut load time from 4s to 1.2s" beats "improved it".</li>
            <li>• Pause instead of saying "um". Silence sounds like thinking.</li>
          </ul>
        </section>
      </aside>
    </div>
  )
}

function VoiceAnswer({ recorder, onSwitchToTyping }: {
  recorder: ReturnType<typeof useRecorder>; onSwitchToTyping: () => void
}) {
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="section-title">Speak your answer</h3>
        <button className="text-xs font-medium text-brand-400 hover:underline"
                onClick={onSwitchToTyping}>
          Type instead
        </button>
      </div>

      <div className="flex items-center gap-4 rounded-xl border border-ink-700 bg-ink-950/50 px-4 py-4">
        <div className="relative grid h-14 w-14 shrink-0 place-items-center">
          {recorder.recording && (
            <span className="absolute inset-0 animate-pulse-ring rounded-full bg-rose-500/40" />
          )}
          <span className={`grid h-12 w-12 place-items-center rounded-full text-xl ${
            recorder.recording ? 'bg-rose-500/25' : 'bg-ink-700'}`}>
            🎙️
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className={`font-mono text-lg ${
              recorder.recording ? 'text-rose-300' : 'text-slate-400'}`}>
              {clockFrom(recorder.elapsed)}
            </span>
            <span className="text-xs text-slate-500">
              {recorder.recording ? 'recording…' : 'ready'}
            </span>
          </div>
          <div className="mt-2 flex h-6 items-end gap-[3px]">
            {Array.from({ length: 28 }).map((_, index) => (
              <span key={index}
                    className={`w-1 rounded-full transition-all duration-100 ${
                      recorder.recording ? 'bg-brand-400' : 'bg-ink-600'}`}
                    style={{
                      height: recorder.recording
                        ? `${8 + Math.abs(Math.sin(index * 0.6 + recorder.elapsed * 5)) *
                             recorder.level * 100}%`
                        : '18%',
                    }} />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 min-h-[96px] rounded-xl border border-ink-700 bg-ink-950/40 p-3.5 text-sm">
        {recorder.transcript || recorder.interim ? (
          <p className="leading-relaxed text-slate-200">
            {recorder.transcript}
            <span className="text-slate-500">{recorder.interim}</span>
          </p>
        ) : (
          <p className="text-slate-500">
            {recorder.liveTranscriptSupported
              ? 'Your words will appear here as you speak.'
              : 'This browser has no live transcription — your recording will be transcribed after you stop.'}
          </p>
        )}
      </div>
    </>
  )
}
