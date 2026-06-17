import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import Layout from './Layout'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'admin', role: 'admin', full_name: 'Admin' }, logout: vi.fn() }),
}))

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout />
    </MemoryRouter>,
  )
}

describe('Layout RTL-aware sidebar', () => {
  it('sidebar uses logical/direction-aware utilities (not hardcoded left/border-r)', () => {
    const { container } = renderLayout()
    const aside = container.querySelector('aside')!
    expect(aside).toBeTruthy()
    const cls = aside.className
    // Logical inline-start positioning and direction-aware hidden transform
    expect(cls).toMatch(/(^|\s)start-0(\s|$)/)
    expect(cls).toContain('rtl:translate-x-full')
    // Must not reuse the physical left-0 anchor that breaks RTL
    expect(cls).not.toMatch(/(^|\s)left-0(\s|$)/)
  })
})
