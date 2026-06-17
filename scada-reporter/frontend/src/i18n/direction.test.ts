import { describe, it, expect, beforeEach } from 'vitest'
import i18n, { dirFor } from './index'

describe('dirFor', () => {
  it('returns rtl for Arabic', () => {
    expect(dirFor('ar')).toBe('rtl')
  })
  it('returns ltr for en/tr/ru/de', () => {
    for (const l of ['en', 'tr', 'ru', 'de']) expect(dirFor(l)).toBe('ltr')
  })
})

describe('document direction follows language', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('sets <html dir=rtl lang=ar> when switching to Arabic', async () => {
    await i18n.changeLanguage('ar')
    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('ar')
  })

  it('reverts to ltr when switching back to English', async () => {
    await i18n.changeLanguage('ar')
    await i18n.changeLanguage('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.documentElement.lang).toBe('en')
  })
})
