/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { getMe, login as apiLogin } from '../api/client'
import i18n from '../i18n'

interface User { id: number; username: string; role: string; full_name: string; language: string; permissions: string[] }

interface AuthCtx {
  user: User | null
  loading: boolean
  login: (u: string, p: string) => Promise<void>
  logout: () => void
  can: (perm: string) => boolean
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => !!localStorage.getItem('token'))

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return
    getMe()
      .then((r) => { setUser(r.data); if (r.data.language) i18n.changeLanguage(r.data.language) })
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setLoading(false))
  }, [])

  const login = async (username: string, password: string) => {
    const r = await apiLogin(username, password)
    localStorage.setItem('token', r.data.access_token)
    const me = await getMe()
    setUser(me.data)
    if (me.data.language) i18n.changeLanguage(me.data.language)
  }

  const logout = () => { localStorage.removeItem('token'); setUser(null) }

  const can = (perm: string) =>
    user?.role === 'admin' || !!user?.permissions?.includes(perm)

  return <Ctx.Provider value={{ user, loading, login, logout, can }}>{children}</Ctx.Provider>
}

export const useAuth = () => {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
