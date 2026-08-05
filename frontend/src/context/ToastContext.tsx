import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

type ToastKind = 'success' | 'error' | 'info'
interface Toast { id: number; kind: ToastKind; message: string }

interface ToastApi {
  push: (message: string, kind?: ToastKind) => void
  success: (message: string) => void
  error: (message: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const STYLES: Record<ToastKind, string> = {
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  error: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
  info: 'border-brand-500/40 bg-brand-500/10 text-brand-400',
}

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = nextId++
    setToasts((current) => [...current, { id, kind, message }])
    // Errors stay longer: they usually contain an instruction to follow.
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, kind === 'error' ? 7000 : 4000)
  }, [])

  const value = useMemo<ToastApi>(() => ({
    push,
    success: (message: string) => push(message, 'success'),
    error: (message: string) => push(message, 'error'),
  }), [push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-full max-w-sm flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={`pointer-events-auto animate-fade-up rounded-xl border px-4 py-3 text-sm
                        shadow-lg shadow-black/40 backdrop-blur ${STYLES[toast.kind]}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context
}
