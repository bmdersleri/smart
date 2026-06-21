import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './Layout'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'admin', role: 'admin', full_name: 'Admin' }, logout: vi.fn(), can: () => false }),
}))

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    </QueryClientProvider>,
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
