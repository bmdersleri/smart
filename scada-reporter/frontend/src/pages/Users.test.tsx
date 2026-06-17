import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
import { listUsers, deleteUser } from '../api/client'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
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

  it('alerts backend detail on delete error', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteUser).mockRejectedValue({
      response: { status: 400, data: { detail: 'Son aktif admin kaldirilamaz' } },
    })

    wrap(<Users />)
    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /delete/i }))

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith('Son aktif admin kaldirilamaz'))

    alertSpy.mockRestore()
  })
})
