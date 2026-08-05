import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, clearToken, getToken, setToken } from '../lib/api'
import type { User } from '../lib/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: {
    email: string; password: string; full_name: string
    target_role: string; experience_level: string
  }) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // On boot, exchange whatever token is in localStorage for the real user.
  // Trusting a cached user object would show a stale name (or a stale admin
  // flag) after the token had already been revoked server-side.
  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    api.me()
      .then(setUserState)
      .catch(() => clearToken())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.login(email, password)
    setToken(response.access_token)
    setUserState(response.user)
  }, [])

  const register = useCallback(async (data: {
    email: string; password: string; full_name: string
    target_role: string; experience_level: string
  }) => {
    const response = await api.register(data)
    setToken(response.access_token)
    setUserState(response.user)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setUserState(null)
  }, [])

  const refresh = useCallback(async () => {
    setUserState(await api.me())
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh, setUser: setUserState }),
    [user, loading, login, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
