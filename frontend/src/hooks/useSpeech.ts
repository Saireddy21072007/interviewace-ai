/**
 * Text-to-speech for the interviewer's questions.
 *
 * Uses the browser's built-in speechSynthesis: no API key, no latency, no
 * per-question cost. For a mock interview that is the right trade - the value
 * is in hearing the question out loud and having to answer immediately, not
 * in the voice sounding human.
 *
 * Every method is a no-op when the API is missing, so a browser without it
 * simply shows the question as text.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export function useSpeech() {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window
  const [speaking, setSpeaking] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const voice = useRef<SpeechSynthesisVoice | null>(null)

  useEffect(() => {
    if (!supported) return
    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices()
      voice.current =
        voices.find((v) => /en-IN/i.test(v.lang)) ??
        voices.find((v) => /en-GB/i.test(v.lang)) ??
        voices.find((v) => v.lang.startsWith('en')) ??
        voices[0] ?? null
    }
    pickVoice()
    // Chrome populates the voice list asynchronously after first paint.
    window.speechSynthesis.onvoiceschanged = pickVoice
    return () => { window.speechSynthesis.onvoiceschanged = null }
  }, [supported])

  const speak = useCallback((text: string) => {
    if (!supported || !enabled || !text) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    if (voice.current) utterance.voice = voice.current
    utterance.rate = 0.98
    utterance.pitch = 1
    utterance.onstart = () => setSpeaking(true)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utterance)
  }, [supported, enabled])

  const stop = useCallback(() => {
    if (!supported) return
    window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [supported])

  // Never leave a question being read aloud after the user navigates away.
  useEffect(() => stop, [stop])

  return { supported, speaking, enabled, setEnabled, speak, stop }
}
