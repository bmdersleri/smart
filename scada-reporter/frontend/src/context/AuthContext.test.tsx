import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

vi.mock('../api/client', () => ({
  getMe: vi.fn(),
  login: vi.fn(),
}))

import { getMe } from '../api/client'

function Probe() {
  const { can } = useAuth()
  return <div>plc:{String(can('plc:manage'))} del:{String(can('report_template:delete'))}</div>
}

describe('AuthContext can()', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'tok')
    vi.mocked(getMe).mockResolvedValue({
      data: {
        id: 1, username: 'op', role: 'operator', full_name: '', language: 'en',
        permissions: ['tag:create', 'plc:manage'],
      },
    } as never)
  })

  it('grants listed perms and denies others', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByText(/plc:true/)).toBeInTheDocument())
    expect(screen.getByText(/del:false/)).toBeInTheDocument()
  })
})
