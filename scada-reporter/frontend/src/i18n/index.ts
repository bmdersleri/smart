import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enCommon from './locales/en/common.json'
import trCommon from './locales/tr/common.json'
import ruCommon from './locales/ru/common.json'
import deCommon from './locales/de/common.json'
import enLogin from './locales/en/login.json'
import trLogin from './locales/tr/login.json'
import ruLogin from './locales/ru/login.json'
import deLogin from './locales/de/login.json'
import enSettings from './locales/en/settings.json'
import trSettings from './locales/tr/settings.json'
import ruSettings from './locales/ru/settings.json'
import deSettings from './locales/de/settings.json'
import enDashboard from './locales/en/dashboard.json'
import trDashboard from './locales/tr/dashboard.json'
import ruDashboard from './locales/ru/dashboard.json'
import deDashboard from './locales/de/dashboard.json'
import enTags from './locales/en/tags.json'
import trTags from './locales/tr/tags.json'
import ruTags from './locales/ru/tags.json'
import deTags from './locales/de/tags.json'
import enTrend from './locales/en/trend.json'
import trTrend from './locales/tr/trend.json'
import ruTrend from './locales/ru/trend.json'
import deTrend from './locales/de/trend.json'
import enReports from './locales/en/reports.json'
import trReports from './locales/tr/reports.json'
import ruReports from './locales/ru/reports.json'
import deReports from './locales/de/reports.json'
import enAdvancedReports from './locales/en/advancedReports.json'
import trAdvancedReports from './locales/tr/advancedReports.json'
import ruAdvancedReports from './locales/ru/advancedReports.json'
import deAdvancedReports from './locales/de/advancedReports.json'
import enPlc from './locales/en/plc.json'
import trPlc from './locales/tr/plc.json'
import ruPlc from './locales/ru/plc.json'
import dePlc from './locales/de/plc.json'
import enMetrics from './locales/en/metrics.json'
import trMetrics from './locales/tr/metrics.json'
import ruMetrics from './locales/ru/metrics.json'
import deMetrics from './locales/de/metrics.json'

export const SUPPORTED_LANGS = ['en', 'tr', 'ru', 'de'] as const
export type Lang = (typeof SUPPORTED_LANGS)[number]

const stored = localStorage.getItem('lang')
const initialLng = (SUPPORTED_LANGS as readonly string[]).includes(stored ?? '') ? (stored as Lang) : 'en'

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon, login: enLogin, settings: enSettings, dashboard: enDashboard, tags: enTags, trend: enTrend, reports: enReports, advancedReports: enAdvancedReports, plc: enPlc, metrics: enMetrics },
    tr: { common: trCommon, login: trLogin, settings: trSettings, dashboard: trDashboard, tags: trTags, trend: trTrend, reports: trReports, advancedReports: trAdvancedReports, plc: trPlc, metrics: trMetrics },
    ru: { common: ruCommon, login: ruLogin, settings: ruSettings, dashboard: ruDashboard, tags: ruTags, trend: ruTrend, reports: ruReports, advancedReports: ruAdvancedReports, plc: ruPlc, metrics: ruMetrics },
    de: { common: deCommon, login: deLogin, settings: deSettings, dashboard: deDashboard, tags: deTags, trend: deTrend, reports: deReports, advancedReports: deAdvancedReports, plc: dePlc, metrics: deMetrics },
  },
  lng: initialLng,
  fallbackLng: 'en',
  ns: ['common', 'login', 'settings', 'dashboard', 'tags', 'trend', 'reports', 'advancedReports', 'plc', 'metrics'],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => { localStorage.setItem('lang', lng) })

export default i18n
