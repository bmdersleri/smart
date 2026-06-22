import { PRESET_KEY, type Preset } from './constants'

export function loadPresets(): Preset[] {
  try {
    return JSON.parse(localStorage.getItem(PRESET_KEY) ?? '[]')
  } catch {
    return []
  }
}

export function storePresets(presets: Preset[]) {
  localStorage.setItem(PRESET_KEY, JSON.stringify(presets))
}
