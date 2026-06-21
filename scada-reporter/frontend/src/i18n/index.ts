import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enCommon from './locales/en/common.json'
import trCommon from './locales/tr/common.json'
import ruCommon from './locales/ru/common.json'
import deCommon from './locales/de/common.json'
import arCommon from './locales/ar/common.json'
import enLogin from './locales/en/login.json'
import trLogin from './locales/tr/login.json'
import ruLogin from './locales/ru/login.json'
import deLogin from './locales/de/login.json'
import arLogin from './locales/ar/login.json'
import enSettings from './locales/en/settings.json'
import trSettings from './locales/tr/settings.json'
import ruSettings from './locales/ru/settings.json'
import deSettings from './locales/de/settings.json'
import arSettings from './locales/ar/settings.json'
import enDashboard from './locales/en/dashboard.json'
import trDashboard from './locales/tr/dashboard.json'
import ruDashboard from './locales/ru/dashboard.json'
import deDashboard from './locales/de/dashboard.json'
import arDashboard from './locales/ar/dashboard.json'
import enTags from './locales/en/tags.json'
import trTags from './locales/tr/tags.json'
import ruTags from './locales/ru/tags.json'
import deTags from './locales/de/tags.json'
import arTags from './locales/ar/tags.json'
import enTrend from './locales/en/trend.json'
import trTrend from './locales/tr/trend.json'
import ruTrend from './locales/ru/trend.json'
import deTrend from './locales/de/trend.json'
import arTrend from './locales/ar/trend.json'
import enReports from './locales/en/reports.json'
import trReports from './locales/tr/reports.json'
import ruReports from './locales/ru/reports.json'
import deReports from './locales/de/reports.json'
import arReports from './locales/ar/reports.json'
import enAdvancedReports from './locales/en/advancedReports.json'
import trAdvancedReports from './locales/tr/advancedReports.json'
import ruAdvancedReports from './locales/ru/advancedReports.json'
import deAdvancedReports from './locales/de/advancedReports.json'
import arAdvancedReports from './locales/ar/advancedReports.json'
import enPlc from './locales/en/plc.json'
import trPlc from './locales/tr/plc.json'
import ruPlc from './locales/ru/plc.json'
import dePlc from './locales/de/plc.json'
import arPlc from './locales/ar/plc.json'
import enMetrics from './locales/en/metrics.json'
import trMetrics from './locales/tr/metrics.json'
import ruMetrics from './locales/ru/metrics.json'
import deMetrics from './locales/de/metrics.json'
import arMetrics from './locales/ar/metrics.json'
import enUsers from './locales/en/users.json'
import trUsers from './locales/tr/users.json'
import ruUsers from './locales/ru/users.json'
import deUsers from './locales/de/users.json'
import arUsers from './locales/ar/users.json'
import enExcelTemplates from './locales/en/excelTemplates.json'
import trExcelTemplates from './locales/tr/excelTemplates.json'
import ruExcelTemplates from './locales/ru/excelTemplates.json'
import deExcelTemplates from './locales/de/excelTemplates.json'
import arExcelTemplates from './locales/ar/excelTemplates.json'
import enPlcHealth from './locales/en/plcHealth.json'
import trPlcHealth from './locales/tr/plcHealth.json'
import ruPlcHealth from './locales/ru/plcHealth.json'
import dePlcHealth from './locales/de/plcHealth.json'
import arPlcHealth from './locales/ar/plcHealth.json'

export const SUPPORTED_LANGS = ['en', 'tr', 'ru', 'de', 'ar'] as const
export type Lang = (typeof SUPPORTED_LANGS)[number]

export const RTL_LANGS = new Set<string>(['ar'])
export function dirFor(lang: string): 'rtl' | 'ltr' {
  return RTL_LANGS.has(lang) ? 'rtl' : 'ltr'
}
function applyDir(lng: string) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lng
    document.documentElement.dir = dirFor(lng)
  }
}

const stored = localStorage.getItem('lang')
const initialLng = (SUPPORTED_LANGS as readonly string[]).includes(stored ?? '') ? (stored as Lang) : 'en'

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon, login: enLogin, settings: enSettings, dashboard: enDashboard, tags: enTags, trend: enTrend, reports: enReports, advancedReports: enAdvancedReports, plc: enPlc, metrics: enMetrics, users: enUsers, excelTemplates: enExcelTemplates, plcHealth: enPlcHealth },
    tr: { common: trCommon, login: trLogin, settings: trSettings, dashboard: trDashboard, tags: trTags, trend: trTrend, reports: trReports, advancedReports: trAdvancedReports, plc: trPlc, metrics: trMetrics, users: trUsers, excelTemplates: trExcelTemplates, plcHealth: trPlcHealth },
    ru: { common: ruCommon, login: ruLogin, settings: ruSettings, dashboard: ruDashboard, tags: ruTags, trend: ruTrend, reports: ruReports, advancedReports: ruAdvancedReports, plc: ruPlc, metrics: ruMetrics, users: ruUsers, excelTemplates: ruExcelTemplates, plcHealth: ruPlcHealth },
    de: { common: deCommon, login: deLogin, settings: deSettings, dashboard: deDashboard, tags: deTags, trend: deTrend, reports: deReports, advancedReports: deAdvancedReports, plc: dePlc, metrics: deMetrics, users: deUsers, excelTemplates: deExcelTemplates, plcHealth: dePlcHealth },
    ar: { common: arCommon, login: arLogin, settings: arSettings, dashboard: arDashboard, tags: arTags, trend: arTrend, reports: arReports, advancedReports: arAdvancedReports, plc: arPlc, metrics: arMetrics, users: arUsers, excelTemplates: arExcelTemplates, plcHealth: arPlcHealth },
  },
  lng: initialLng,
  fallbackLng: 'en',
  ns: ['common', 'login', 'settings', 'dashboard', 'tags', 'trend', 'reports', 'advancedReports', 'plc', 'metrics', 'users', 'excelTemplates', 'plcHealth'],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => {
  localStorage.setItem('lang', lng)
  applyDir(lng)
})

applyDir(initialLng)

export default i18n
