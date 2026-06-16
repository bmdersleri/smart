import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import i18n from '../i18n'
import Login from './Login'

vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: vi.fn() }) }))

const renderLogin = () => render(<MemoryRouter><Login /></MemoryRouter>)

describe('Login i18n', () => {
  beforeEach(async () => { await i18n.changeLanguage('en') })

  it('renders the English submit label', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: 'Log In' })).toBeTruthy()
  })

  it('renders the Turkish submit label after switch', async () => {
    await i18n.changeLanguage('tr')
    renderLogin()
    expect(screen.getByRole('button', { name: 'Giriş Yap' })).toBeTruthy()
  })

  it('shows no raw translation keys', () => {
    renderLogin()
    expect(document.body.textContent).not.toMatch(/login:/)
  })
})
