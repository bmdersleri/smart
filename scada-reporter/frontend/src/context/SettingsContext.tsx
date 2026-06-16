/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useEffect } from 'react'

const SETTINGS_KEY = 'scada_settings'

type Theme = 'dark' | 'light'

interface Settings {
  trendChartHeight: number
  theme: Theme
}

const defaults: Settings = {
  trendChartHeight: 1000,
  theme: 'dark',
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (raw) return { ...defaults, ...JSON.parse(raw) }
  } catch { /* ignore parse errors */ }
  return defaults
}

interface SettingsCtx extends Settings {
  set: <K extends keyof Settings>(key: K, value: Settings[K]) => void
  reset: () => void
}

const Ctx = createContext<SettingsCtx | null>(null)

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<Settings>(load)

  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  }, [settings])

  // Tema sınıfını <html> köküne uygula (CSS override'ları html.light altında)
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('light', settings.theme === 'light')
    root.classList.toggle('dark', settings.theme !== 'light')
  }, [settings.theme])

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  function reset() {
    setSettings(defaults)
  }

  return <Ctx.Provider value={{ ...settings, set, reset }}>{children}</Ctx.Provider>
}

export function useSettings() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useSettings must be used within SettingsProvider')
  return ctx
}
