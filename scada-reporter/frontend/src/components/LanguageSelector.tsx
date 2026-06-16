import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import { SUPPORTED_LANGS } from '../i18n'
import { updateMe } from '../api/client'

const LABELS: Record<string, string> = { en: 'English', tr: 'Türkçe', ru: 'Русский', de: 'Deutsch' }

export default function LanguageSelector() {
  const { i18n } = useTranslation()

  const onChange = (lang: string) => {
    i18n.changeLanguage(lang)
    updateMe(lang).catch(() => { /* applied locally + cached; ignore persistence error */ })
  }

  return (
    <div className="flex items-center gap-2">
      <Globe className="w-4 h-4 text-gray-400" />
      <select
        value={i18n.language}
        onChange={(e) => onChange(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
      >
        {SUPPORTED_LANGS.map((l) => (<option key={l} value={l}>{LABELS[l]}</option>))}
      </select>
    </div>
  )
}
