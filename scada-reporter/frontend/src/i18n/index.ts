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

export const SUPPORTED_LANGS = ['en', 'tr', 'ru', 'de'] as const
export type Lang = (typeof SUPPORTED_LANGS)[number]

const stored = localStorage.getItem('lang')
const initialLng = (SUPPORTED_LANGS as readonly string[]).includes(stored ?? '') ? (stored as Lang) : 'en'

i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon, login: enLogin, settings: enSettings },
    tr: { common: trCommon, login: trLogin, settings: trSettings },
    ru: { common: ruCommon, login: ruLogin, settings: ruSettings },
    de: { common: deCommon, login: deLogin, settings: deSettings },
  },
  lng: initialLng,
  fallbackLng: 'en',
  ns: ['common', 'login', 'settings'],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => { localStorage.setItem('lang', lng) })

export default i18n
