import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Users from './Users'

vi.mock('../api/client', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  patchUser: vi.fn(),
  resetUserPassword: vi.fn(),
  deleteUser: vi.fn(),
}))
import { listUsers } from '../api/client'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('Users page', () => {
  beforeEach(() => {
    vi.mocked(listUsers).mockResolvedValue({
      data: [
        { id: 1, username: 'admin', email: 'a@a', full_name: 'Admin', role: 'admin',
          is_active: true, permission_overrides: {}, permissions: [] },
      ],
    } as never)
  })

  it('renders the user list', async () => {
    wrap(<Users />)
    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument())
  })
})
