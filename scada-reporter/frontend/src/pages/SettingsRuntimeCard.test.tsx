import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n'
import SettingsRuntimeCard from './SettingsRuntimeCard'

const status = {
  controls_enabled: true,
  backend: { status: 'ok', uptime_seconds: 65, started_at: '2026-06-27T08:00:00+00:00' },
  collector: {
    configured: true,
    running: false,
    poller_running: false,
    opcua_running: false,
    monitor_running: false,
  },
  scheduler: { configured: true, running: true },
}

const getRuntimeStatus = vi.fn()
const startCollector = vi.fn()
const stopCollector = vi.fn()
const startScheduler = vi.fn()
const stopScheduler = vi.fn()

vi.mock('../api/client', () => ({
  getRuntimeStatus: () => getRuntimeStatus(),
  startCollector: () => startCollector(),
  stopCollector: () => stopCollector(),
  startScheduler: () => startScheduler(),
  stopScheduler: () => stopScheduler(),
}))

describe('SettingsRuntimeCard', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    getRuntimeStatus.mockReset()
    startCollector.mockReset()
    stopCollector.mockReset()
    startScheduler.mockReset()
    stopScheduler.mockReset()
    getRuntimeStatus.mockResolvedValue({ data: status })
    startCollector.mockResolvedValue({ data: { ...status, collector: { ...status.collector, running: true } } })
    stopScheduler.mockResolvedValue({ data: { ...status, scheduler: { ...status.scheduler, running: false } } })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('renders runtime status', async () => {
    render(<SettingsRuntimeCard />)
    expect(await screen.findByText('Runtime Controls')).toBeInTheDocument()
    expect(screen.getByText('Collector')).toBeInTheDocument()
    expect(screen.getByText('Scheduler')).toBeInTheDocument()
    expect(screen.getByText('1m 5s')).toBeInTheDocument()
    expect(screen.getByText(/Last updated/)).toBeInTheDocument()
  })

  it('starts stopped collector', async () => {
    render(<SettingsRuntimeCard />)
    await screen.findByText('Collector')
    fireEvent.click(screen.getAllByText('Start')[0])

    await waitFor(() => expect(startCollector).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Collector started.')).toBeInTheDocument()
  })

  it('stops running scheduler', async () => {
    render(<SettingsRuntimeCard />)
    await screen.findByText('Scheduler')
    fireEvent.click(screen.getAllByText('Stop')[0])

    expect(window.confirm).toHaveBeenCalledWith('Stop scheduler? Scheduled reports will pause.')
    await waitFor(() => expect(stopScheduler).toHaveBeenCalledTimes(1))
  })

  it('does not stop scheduler when confirmation is canceled', async () => {
    vi.mocked(window.confirm).mockReturnValue(false)

    render(<SettingsRuntimeCard />)
    await screen.findByText('Scheduler')
    fireEvent.click(screen.getAllByText('Stop')[0])

    expect(window.confirm).toHaveBeenCalledWith('Stop scheduler? Scheduled reports will pause.')
    expect(stopScheduler).not.toHaveBeenCalled()
  })

  it('auto-refreshes status while mounted', async () => {
    vi.useFakeTimers()
    render(<SettingsRuntimeCard />)

    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByText('Collector')).toBeInTheDocument()
    expect(getRuntimeStatus).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(10_000)
      await Promise.resolve()
    })

    expect(getRuntimeStatus).toHaveBeenCalledTimes(2)
  })

  it('includes HTTP status and detail in load errors', async () => {
    getRuntimeStatus.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 503, data: { detail: 'runtime unavailable' } },
    })

    render(<SettingsRuntimeCard />)

    expect(await screen.findByText('Runtime status could not be loaded. (503: runtime unavailable)')).toBeInTheDocument()
  })
})
