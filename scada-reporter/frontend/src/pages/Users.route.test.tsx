import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { AdminRoute } from '../App'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'operator' }, loading: false }),
}))

// Stub react-i18next so AdminRoute's t('loading') call doesn't fail
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({ t: (k: string) => k }),
  }
})

function renderWithRouter(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/users"
          element={
            <AdminRoute>
              <div>Users Admin Page</div>
            </AdminRoute>
          }
        />
        <Route path="/" element={<div>Home Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AdminRoute guard', () => {
  it('redirects operator away from /users and shows home instead', () => {
    renderWithRouter('/users')
    expect(screen.queryByText('Users Admin Page')).not.toBeInTheDocument()
    expect(screen.getByText('Home Page')).toBeInTheDocument()
  })
})
