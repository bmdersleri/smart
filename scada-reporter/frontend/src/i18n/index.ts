import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enCommon from './locales/en/common.json'
import trCommon from './locales/tr/common.json'
import ruCommon from './locales/ru/common.json'
import deCommon from './locales/de/common.json'

export const SUPPORTED_LANGS = ['en', 'tr', 'ru', 'de'] as const
export type Lang = (typeof SUPPORTED_LANGS)[number]

const stored = localStorage.getItem('lang')
const initialLng = (SUPPORTED_LANGS as readonly string[]).includes(stored ?? '') ? (stored as Lang) : 'en'

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon },
    tr: { common: trCommon },
    ru: { common: ruCommon },
    de: { common: deCommon },
  },
  lng: initialLng,
  fallbackLng: 'en',
  ns: ['common'],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => { localStorage.setItem('lang', lng) })

export default i18n
