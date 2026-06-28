import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import LanguageSelector from './LanguageSelector'
import LicenseBadge from './LicenseBadge'
import PlcAlertBadge from './PlcAlertBadge'
import SmartReportIcon from './SmartReportIcon'

const nav = [
  { to: '/', labelKey: 'nav_dashboard' },
  { to: '/tags', labelKey: 'nav_tags' },
  { to: '/plc', labelKey: 'nav_plc' },
  { to: '/plc-health', labelKey: 'nav_plc_health' },
  { to: '/trend', labelKey: 'nav_trend' },
  { to: '/reports', labelKey: 'nav_reports' },
  { to: '/advanced-reports', labelKey: 'nav_advanced_reports' },
  { to: '/excel-templates', labelKey: 'nav_excel_templates' },
  { to: '/metrics', labelKey: 'nav_metrics' },
  { to: '/grafana', labelKey: 'nav_grafana' },
  { to: '/lab', labelKey: 'nav_lab' },
  { to: '/settings', labelKey: 'nav_settings' },
]

export default function Layout() {
  const { t } = useTranslation('common')
  const { user, logout } = useAuth()
  const [mobileNav, setMobileNav] = useState(false)

  return (
    <div className="flex h-screen bg-gray-950 bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(14,116,144,0.15),rgba(0,0,0,0))] overflow-hidden">
      {/* Mobile backdrop overlay */}
      {mobileNav && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 md:hidden transition-opacity"
          onClick={() => setMobileNav(false)}
        />
      )}
      {/* Sidebar */}
      <aside
        className={`w-64 bg-gray-900/60 backdrop-blur-xl border-e border-white/5 flex flex-col fixed md:static inset-y-0 start-0 z-40 transform transition-transform duration-300 ease-out md:translate-x-0 ${
          mobileNav ? 'translate-x-0 shadow-2xl' : 'max-md:-translate-x-full max-md:rtl:translate-x-full'
        }`}
      >
        <div className="p-5 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 flex items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 shadow-lg shadow-cyan-500/20 flex-shrink-0">
              <SmartReportIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <p className="text-white font-bold tracking-wide text-sm leading-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-300">EKONT SMART</p>
              <p className="text-cyan-400 font-medium text-[11px] tracking-wider uppercase mt-0.5">{t('app_subtitle')}</p>
            </div>
          </div>
          <PlcAlertBadge />
        </div>

        <nav className="flex-1 p-3 space-y-1.5 overflow-y-auto custom-scrollbar">
          {nav.map(({ to, labelKey }) => (
            <NavLink
              key={to} to={to} end={to === '/'}
              onClick={() => setMobileNav(false)}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]'
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`
              }
            >
              <SmartReportIcon className={`w-5 h-5 flex-shrink-0 transition-colors ${
                // Optional: Make icon match active state color specifically or leave inherited
                'opacity-80 group-hover:opacity-100'
              }`} />
              {t(labelKey)}
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink
              to="/users"
              onClick={() => setMobileNav(false)}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]'
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`
              }
            >
              <SmartReportIcon className="w-4 h-4 flex-shrink-0" />
              {t('nav_users')}
            </NavLink>
          )}
        </nav>

        <div className="p-4 border-t border-white/5 bg-gray-900/30">
          <LicenseBadge />
          <div className="flex items-center gap-3 px-2 py-2 mb-2 rounded-lg hover:bg-white/5 transition-colors cursor-pointer">
            <div className="w-8 h-8 bg-gradient-to-br from-gray-700 to-gray-600 rounded-full flex items-center justify-center text-sm text-white font-medium shadow-inner border border-gray-500/30">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.full_name || user?.username}</p>
              <p className="text-xs text-gray-500 capitalize">{user?.role}</p>
            </div>
          </div>
          <div className="px-2 py-1 mb-2">
            <LanguageSelector />
          </div>
          <button onClick={logout} className="w-full text-start px-3 py-2 text-sm font-medium text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-colors">
            {t('logout')}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto relative">
        {/* Mobile top bar */}
        <div className="md:hidden sticky top-0 z-20 flex items-center gap-3 bg-gray-900/80 backdrop-blur-md border-b border-white/5 px-4 py-3">
          <button
            onClick={() => setMobileNav(true)}
            className="text-gray-300 hover:text-white"
            aria-label={t('menu_open')}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="flex items-center gap-2 text-white font-semibold text-sm flex-1">
            <span className="w-7 h-7 flex items-center justify-center flex-shrink-0">
              <SmartReportIcon className="w-6 h-6" />
            </span>
            EKONT SMART REPORT
          </span>
          <PlcAlertBadge />
        </div>
        <Outlet />
      </main>
    </div>
  )
}
