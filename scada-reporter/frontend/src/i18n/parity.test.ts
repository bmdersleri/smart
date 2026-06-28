import { describe, it, expect } from 'vitest'

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

import enPlcHealth from './locales/en/plcHealth.json'
import trPlcHealth from './locales/tr/plcHealth.json'
import ruPlcHealth from './locales/ru/plcHealth.json'
import dePlcHealth from './locales/de/plcHealth.json'
import arPlcHealth from './locales/ar/plcHealth.json'

import enCompliance from './locales/en/compliance.json'
import trCompliance from './locales/tr/compliance.json'
import ruCompliance from './locales/ru/compliance.json'
import deCompliance from './locales/de/compliance.json'
import arCompliance from './locales/ar/compliance.json'

type Dict = Record<string, unknown>

const NAMESPACES: Record<string, Record<string, Dict>> = {
  common: { en: enCommon, tr: trCommon, ru: ruCommon, de: deCommon, ar: arCommon },
  login: { en: enLogin, tr: trLogin, ru: ruLogin, de: deLogin, ar: arLogin },
  settings: { en: enSettings, tr: trSettings, ru: ruSettings, de: deSettings, ar: arSettings },
  dashboard: { en: enDashboard, tr: trDashboard, ru: ruDashboard, de: deDashboard, ar: arDashboard },
  tags: { en: enTags, tr: trTags, ru: ruTags, de: deTags, ar: arTags },
  trend: { en: enTrend, tr: trTrend, ru: ruTrend, de: deTrend, ar: arTrend },
  reports: { en: enReports, tr: trReports, ru: ruReports, de: deReports, ar: arReports },
  advancedReports: {
    en: enAdvancedReports,
    tr: trAdvancedReports,
    ru: ruAdvancedReports,
    de: deAdvancedReports,
    ar: arAdvancedReports,
  },
  plc: { en: enPlc, tr: trPlc, ru: ruPlc, de: dePlc, ar: arPlc },
  metrics: { en: enMetrics, tr: trMetrics, ru: ruMetrics, de: deMetrics, ar: arMetrics },
  users: { en: enUsers, tr: trUsers, ru: ruUsers, de: deUsers, ar: arUsers },
  plcHealth: { en: enPlcHealth, tr: trPlcHealth, ru: ruPlcHealth, de: dePlcHealth, ar: arPlcHealth },
  compliance: { en: enCompliance, tr: trCompliance, ru: ruCompliance, de: deCompliance, ar: arCompliance },
}

const TARGET_LANGS = ['tr', 'ru', 'de', 'ar'] as const

// Recursively collect dotted key paths so nested objects are compared too.
function collectKeys(obj: Dict, prefix = ''): string[] {
  const out: string[] = []
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...collectKeys(v as Dict, path))
    } else {
      out.push(path)
    }
  }
  return out
}

// Recursively collect every leaf string value keyed by its dotted path.
function collectStrings(obj: Dict, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, collectStrings(v as Dict, path))
    } else if (typeof v === 'string') {
      out[path] = v
    }
  }
  return out
}

function placeholders(value: string): string[] {
  const tokens = value.match(/\{\{\s*\w+\s*\}\}/g) ?? []
  return tokens.map((t) => t.replace(/\s+/g, '')).sort()
}

describe('i18n key parity', () => {
  for (const [ns, langs] of Object.entries(NAMESPACES)) {
    const enKeys = collectKeys(langs.en).sort()
    for (const lang of TARGET_LANGS) {
      it(`${ns}: ${lang} has the same keys as en`, () => {
        expect(collectKeys(langs[lang]).sort()).toEqual(enKeys)
      })
    }
  }
})

describe('i18n placeholder parity', () => {
  for (const [ns, langs] of Object.entries(NAMESPACES)) {
    const enStrings = collectStrings(langs.en)
    for (const lang of TARGET_LANGS) {
      it(`${ns}: ${lang} has matching {{placeholders}} per key`, () => {
        const langStrings = collectStrings(langs[lang])
        const mismatches: string[] = []
        for (const [key, enVal] of Object.entries(enStrings)) {
          const enPh = placeholders(enVal)
          const langVal = langStrings[key]
          if (langVal === undefined) continue // key parity test covers this
          const langPh = placeholders(langVal)
          if (JSON.stringify(enPh) !== JSON.stringify(langPh)) {
            mismatches.push(`${key}: en=[${enPh.join(',')}] ${lang}=[${langPh.join(',')}]`)
          }
        }
        expect(mismatches).toEqual([])
      })
    }
  }
})
