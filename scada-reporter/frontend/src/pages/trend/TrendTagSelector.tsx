import type { Dispatch, SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import type { Tag } from '../../api/client'
import { COLORS, HOURS, type Preset } from './constants'
import { GroupTree } from './GroupTree'

interface TrendTagSelectorProps {
  panelOpen: boolean
  tagSearch: string
  setTagSearch: (value: string) => void
  selectorMode: 'flat' | 'auto' | 'manual'
  setSelectorMode: (mode: 'flat' | 'auto' | 'manual') => void
  selected: number[]
  setSelected: Dispatch<SetStateAction<number[]>>
  tags: Tag[]
  filteredTags: Tag[]
  presets: Preset[]
  savingName: string | null
  setSavingName: Dispatch<SetStateAction<string | null>>
  savePreset: () => void
  loadPreset: (preset: Preset) => void
  deletePreset: (name: string) => void
  toggleTag: (id: number) => void
}

export function TrendTagSelector({
  panelOpen,
  tagSearch,
  setTagSearch,
  selectorMode,
  setSelectorMode,
  selected,
  setSelected,
  tags,
  filteredTags,
  presets,
  savingName,
  setSavingName,
  savePreset,
  loadPreset,
  deletePreset,
  toggleTag,
}: TrendTagSelectorProps) {
  const { t } = useTranslation(['trend', 'common'])

  return (
    <div
      className={`bg-gray-900 border border-gray-800 rounded-xl flex-shrink-0 space-y-2 overflow-y-auto transition-all duration-200 ${
        panelOpen ? 'w-52 p-3' : 'w-0 p-0'
      }`}
    >
      <input
        value={tagSearch}
        onChange={(e) => setTagSearch(e.target.value)}
        placeholder={t('search_placeholder')}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
      />

      <div className="flex gap-1 bg-gray-800 rounded-lg p-0.5">
        {(
          [
            ['flat', t('mode_flat')],
            ['auto', t('mode_auto')],
            ['manual', t('mode_manual')],
          ] as const
        ).map(([mode, label]) => (
          <button
            key={mode}
            onClick={() => setSelectorMode(mode)}
            className={`flex-1 px-1 py-1 text-[11px] rounded-md transition-colors ${
              selectorMode === mode ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {selected.length > 0 && savingName === null && (
        <div className="flex gap-1.5">
          <button
            onClick={() => setSavingName('')}
            className="flex-1 px-2 py-1 text-xs bg-blue-700/40 hover:bg-blue-700/60 text-blue-300 rounded-lg transition-colors"
          >
            {t('common:save')}
          </button>
          <button
            onClick={() => setSelected([])}
            className="flex-1 px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-red-400 rounded-lg transition-colors"
          >
            {t('clear_all')}
          </button>
        </div>
      )}

      {savingName !== null && (
        <div className="space-y-1">
          <input
            autoFocus
            value={savingName}
            onChange={(e) => setSavingName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') savePreset()
              if (e.key === 'Escape') setSavingName(null)
            }}
            placeholder={t('preset_name_placeholder')}
            className="w-full bg-gray-800 border border-blue-600 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none"
          />
          <div className="flex gap-1">
            <button
              onClick={savePreset}
              disabled={!savingName.trim()}
              className="flex-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-lg transition-colors"
            >
              {t('common:save')}
            </button>
            <button
              onClick={() => setSavingName(null)}
              className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg transition-colors"
            >
              {t('common:cancel')}
            </button>
          </div>
        </div>
      )}

      {presets.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 uppercase tracking-wide px-1">{t('saved_presets')}</p>
          {presets.map((preset) => {
            const hourKey = HOURS.find((h) => h.v === preset.hours)?.key

            return (
              <div key={preset.name} className="flex items-center gap-1 group">
                <button
                  onClick={() => loadPreset(preset)}
                  className="flex-1 text-start px-2 py-1 rounded-lg text-xs text-gray-300 hover:bg-gray-800 hover:text-white transition-colors truncate"
                  title={`${preset.tag_ids.length} tag · ${hourKey ? t(hourKey) : `${preset.hours}h`}`}
                >
                  {preset.name}
                </button>
                <button
                  onClick={() => deletePreset(preset.name)}
                  className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 text-xs transition-all px-1"
                  title={t('common:delete')}
                >
                  x
                </button>
              </div>
            )
          })}
          <div className="border-t border-gray-800 pt-1" />
        </div>
      )}

      <p className="text-xs text-gray-500 uppercase tracking-wide px-1">{t('select_tags')}</p>
      {selectorMode === 'flat' ? (
        <div className="space-y-1">
          {filteredTags.length === 0 && <p className="text-gray-500 text-xs px-1">{t('no_match')}</p>}
          {filteredTags.map((tag) => {
            const selectedIndex = selected.indexOf(tag.id)
            const color = selectedIndex >= 0 ? COLORS[selectedIndex % COLORS.length] : '#6b7280'

            return (
              <button
                key={tag.id}
                onClick={() => toggleTag(tag.id)}
                className={`w-full text-start px-2 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                  selectedIndex >= 0
                    ? 'bg-gray-800/60 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0 transition-colors"
                  style={{ backgroundColor: color }}
                />
                <span className="truncate">{tag.name}</span>
              </button>
            )
          })}
        </div>
      ) : (
        <GroupTree mode={selectorMode} tags={tags} selected={selected} onToggle={toggleTag} />
      )}
    </div>
  )
}
