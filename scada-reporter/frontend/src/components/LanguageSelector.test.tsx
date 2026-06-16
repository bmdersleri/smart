import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import i18n from '../i18n'
import LanguageSelector from './LanguageSelector'

vi.mock('../api/client', () => ({
  updateMe: vi.fn().mockResolvedValue({ data: { language: 'tr' } }),
}))

describe('LanguageSelector', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('renders all four languages', () => {
    render(<LanguageSelector />)
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.options).toHaveLength(4)
  })

  it('changes i18n language and persists on select', async () => {
    const { updateMe } = await import('../api/client')
    render(<LanguageSelector />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'tr' } })
    expect(i18n.language).toBe('tr')
    expect(updateMe).toHaveBeenCalledWith('tr')
  })
})
