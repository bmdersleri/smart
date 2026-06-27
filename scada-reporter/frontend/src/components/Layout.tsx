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
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Mobile backdrop overlay */}
      {mobileNav && (
        <div
          className="fixed inset-0 bg-black/60 z-30 md:hidden"
          onClick={() => setMobileNav(false)}
        />
      )}
      {/* Sidebar */}
      <aside
        className={`w-56 bg-gray-900 border-e border-gray-800 flex flex-col fixed md:static inset-y-0 start-0 z-40 transform transition-transform duration-200 md:translate-x-0 ${
          mobileNav ? 'translate-x-0' : 'max-md:-translate-x-full max-md:rtl:translate-x-full'
        }`}
      >
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
              <SmartReportIcon className="w-7 h-7" />
            </div>
            <div>
              <p className="text-white font-semibold text-sm leading-tight">EKONT SMART REPORT</p>
              <p className="text-gray-500 text-xs">{t('app_subtitle')}</p>
            </div>
          </div>
          <PlcAlertBadge />
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {nav.map(({ to, labelKey }) => (
            <NavLink
              key={to} to={to} end={to === '/'}
              onClick={() => setMobileNav(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <SmartReportIcon className="w-4 h-4 flex-shrink-0" />
              {t(labelKey)}
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink
              to="/users"
              onClick={() => setMobileNav(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <SmartReportIcon className="w-4 h-4 flex-shrink-0" />
              {t('nav_users')}
            </NavLink>
          )}
        </nav>

        <div className="p-3 border-t border-gray-800">
          <LicenseBadge />
          <div className="flex items-center gap-2 px-2 py-1.5 mb-1">
            <div className="w-7 h-7 bg-gray-700 rounded-full flex items-center justify-center text-xs text-gray-300 font-medium">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white truncate">{user?.full_name || user?.username}</p>
              <p className="text-xs text-gray-500 capitalize">{user?.role}</p>
            </div>
          </div>
          <div className="px-2 py-1.5 mb-1">
            <LanguageSelector />
          </div>
          <button onClick={logout} className="w-full text-start px-3 py-1.5 text-sm text-gray-400 hover:text-red-400 hover:bg-gray-800 rounded-lg transition-colors">
            {t('logout')}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        {/* Mobile top bar */}
        <div className="md:hidden sticky top-0 z-20 flex items-center gap-3 bg-gray-900 border-b border-gray-800 px-4 py-3">
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
