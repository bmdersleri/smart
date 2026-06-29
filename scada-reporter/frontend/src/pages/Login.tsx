import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { getLive } from '../api/client'
import { backendStatus } from '../utils/backendStatus'
import SmartReportIcon from '../components/SmartReportIcon'

const STATUS_STYLE: Record<string, { dot: string; text: string }> = {
  online: { dot: 'bg-green-400', text: 'text-green-400' },
  offline: { dot: 'bg-red-500', text: 'text-red-400' },
  checking: { dot: 'bg-gray-500', text: 'text-gray-500' },
}

export default function Login() {
  const { t } = useTranslation('login')
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const probe = useQuery({
    queryKey: ['backend-live'],
    queryFn: () => getLive().then((r) => r.data),
    refetchInterval: 5000,
    retry: false,
  })
  const status = backendStatus({ isLoading: probe.isLoading, isError: probe.isError })

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      nav('/')
    } catch {
      setError(t('error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-cyan-950/20 via-gray-950 to-gray-950 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative background glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] bg-cyan-500/10 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-sm relative z-10">
        <div className="login-heading text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 mb-4 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/20 shadow-lg shadow-cyan-500/10">
            <SmartReportIcon className="w-10 h-10 text-cyan-400" />
          </div>
          <h1 className="text-2xl font-bold text-white">EKONT SMART REPORT</h1>
          <p className="text-gray-400 text-sm mt-1">{t('subtitle')}</p>
          <div className="inline-flex items-center gap-1.5 mt-3 text-xs">
            <span className={`w-2 h-2 rounded-full ${STATUS_STYLE[status].dot} ${status === 'online' ? 'animate-pulse' : ''}`} />
            <span className={STATUS_STYLE[status].text}>{t(`backend_${status}`)}</span>
          </div>
        </div>

        <form onSubmit={submit} className="login-card bg-surface-raised/40 backdrop-blur-2xl rounded-3xl p-8 space-y-5 border border-white/10 shadow-2xl shadow-black/50">
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('username')}</label>
            <input
              className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all"
              value={username} onChange={(e) => setUsername(e.target.value)}
              placeholder="admin" autoComplete="username" required
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('password')}</label>
            <input
              type="password"
              className="w-full bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-hidden focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all"
              value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••" autoComplete="current-password" required
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit" disabled={loading}
            className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 text-white font-bold tracking-wide py-3 rounded-xl transition-all shadow-lg shadow-cyan-500/25 hover:shadow-cyan-500/40 active:scale-[0.98]"
          >
            {loading ? t('submitting') : t('submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
