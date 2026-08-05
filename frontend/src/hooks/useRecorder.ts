/**
 * Microphone recording + live transcription for the voice interview.
 *
 * Two things run at once while the candidate speaks:
 *
 *   MediaRecorder  captures the audio itself, which is uploaded and kept so a
 *                  better model can re-transcribe the interview later.
 *   SpeechRecognition (Web Speech API) produces a live transcript, which is
 *                  what makes the interview feel real - words appear as you
 *                  talk instead of after a round trip.
 *
 * The Web Speech API is Chrome/Edge only. When it is unavailable we still
 * record audio and let the server transcribe it, and the UI tells the user
 * their words will appear after they stop instead of live. The one thing we
 * never do is block the interview on it.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

// Minimal typings - SpeechRecognition is not in the standard TS DOM lib.
interface SpeechRecognitionAlternative { transcript: string; confidence: number }
interface SpeechRecognitionResult {
  isFinal: boolean
  length: number
  [index: number]: SpeechRecognitionAlternative
}
interface SpeechRecognitionEvent extends Event {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionResult }
}
interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: Event) => void) | null
  onend: (() => void) | null
}
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export interface RecorderState {
  supported: boolean
  liveTranscriptSupported: boolean
  recording: boolean
  elapsed: number
  transcript: string
  interim: string
  level: number
  error: string | null
  start: () => Promise<void>
  stop: () => Promise<{ blob: Blob | null; transcript: string; duration: number }>
  reset: () => void
  setTranscript: (value: string) => void
}

export function useRecorder(): RecorderState {
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [transcript, setTranscript] = useState('')
  const [interim, setInterim] = useState('')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const stream = useRef<MediaStream | null>(null)
  const recognition = useRef<SpeechRecognitionLike | null>(null)
  const finalText = useRef('')
  const startedAt = useRef(0)
  const timer = useRef<number | null>(null)
  const audioContext = useRef<AudioContext | null>(null)
  const meterFrame = useRef<number | null>(null)

  const supported =
    typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'
  const liveTranscriptSupported = getSpeechRecognition() !== null

  const cleanup = useCallback(() => {
    if (timer.current) { window.clearInterval(timer.current); timer.current = null }
    if (meterFrame.current) { cancelAnimationFrame(meterFrame.current); meterFrame.current = null }
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
    audioContext.current?.close().catch(() => undefined)
    audioContext.current = null
    setLevel(0)
  }, [])

  useEffect(() => cleanup, [cleanup])

  const start = useCallback(async () => {
    setError(null)
    finalText.current = ''
    setTranscript('')
    setInterim('')
    chunks.current = []

    if (!supported) {
      setError('This browser cannot record audio. Use the "Type instead" option.')
      return
    }

    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
    } catch {
      setError('Microphone permission was denied. Allow it in the address bar, or type your answer.')
      return
    }

    // --- audio level meter, purely so the candidate can see they are heard ---
    try {
      audioContext.current = new AudioContext()
      const source = audioContext.current.createMediaStreamSource(stream.current)
      const analyser = audioContext.current.createAnalyser()
      analyser.fftSize = 512
      source.connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => {
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (const value of data) sum += (value - 128) ** 2
        setLevel(Math.min(1, Math.sqrt(sum / data.length) / 40))
        meterFrame.current = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      // A missing level meter is cosmetic; recording continues without it.
    }

    const recorder = new MediaRecorder(stream.current)
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.current.push(event.data)
    }
    recorder.start(250)
    mediaRecorder.current = recorder

    const Recognition = getSpeechRecognition()
    if (Recognition) {
      const engine = new Recognition()
      engine.continuous = true
      engine.interimResults = true
      engine.lang = 'en-IN'
      engine.onresult = (event: SpeechRecognitionEvent) => {
        let interimText = ''
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i]
          if (result.isFinal) finalText.current += `${result[0].transcript} `
          else interimText += result[0].transcript
        }
        setTranscript(finalText.current)
        setInterim(interimText)
      }
      engine.onerror = () => undefined  // 'no-speech' fires constantly; not an error worth showing
      engine.onend = () => {
        // Chrome stops recognition after a pause. Restart while still recording
        // so a thoughtful silence does not silently end the transcript.
        if (mediaRecorder.current?.state === 'recording') {
          try { engine.start() } catch { /* already starting */ }
        }
      }
      try { engine.start() } catch { /* ignore double-start */ }
      recognition.current = engine
    }

    startedAt.current = Date.now()
    setElapsed(0)
    setRecording(true)
    timer.current = window.setInterval(
      () => setElapsed((Date.now() - startedAt.current) / 1000), 200)
  }, [supported])

  const stop = useCallback(async () => {
    const duration = (Date.now() - startedAt.current) / 1000
    setRecording(false)

    recognition.current?.stop()
    recognition.current = null

    const blob = await new Promise<Blob | null>((resolve) => {
      const recorder = mediaRecorder.current
      if (!recorder || recorder.state === 'inactive') return resolve(null)
      recorder.onstop = () => resolve(new Blob(chunks.current, { type: 'audio/webm' }))
      recorder.stop()
    })

    mediaRecorder.current = null
    cleanup()

    const text = (finalText.current + interim).trim()
    setTranscript(text)
    setInterim('')
    return { blob, transcript: text, duration }
  }, [cleanup, interim])

  const reset = useCallback(() => {
    finalText.current = ''
    setTranscript('')
    setInterim('')
    setElapsed(0)
    setError(null)
  }, [])

  return {
    supported, liveTranscriptSupported, recording, elapsed, transcript, interim,
    level, error, start, stop, reset,
    setTranscript: (value: string) => { finalText.current = value; setTranscript(value) },
  }
}
