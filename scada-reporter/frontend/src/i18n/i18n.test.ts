import { describe, it, expect, beforeAll } from 'vitest'
import i18n from './index'

describe('i18n', () => {
  beforeAll(async () => { await i18n.changeLanguage('en') })

  it('returns the English string for a known key', () => {
    expect(i18n.t('common:save')).toBe('Save')
  })

  it('switches language', async () => {
    await i18n.changeLanguage('tr')
    expect(i18n.t('common:save')).toBe('Kaydet')
  })

  it('falls back to English for a missing key in another language', async () => {
    await i18n.changeLanguage('ru')
    expect(i18n.t('common:save')).toBe('Сохранить')
  })
})
