import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../client'
import { getPlcIncidents, getIncidentSummary, ackIncident } from '../client'

describe('plc health api', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('getPlcIncidents passes open + plc query params', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    await getPlcIncidents({ open: true, plc: '10.0.0.1' })
    expect(spy).toHaveBeenCalledWith('/plc/incidents?open=true&plc=10.0.0.1')
  })

  it('getIncidentSummary hits summary endpoint', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { open_total: 0, critical: 0, warning: 0 } } as never)
    await getIncidentSummary()
    expect(spy).toHaveBeenCalledWith('/plc/incidents/summary')
  })

  it('ackIncident posts to ack endpoint', async () => {
    const spy = vi.spyOn(api, 'post').mockResolvedValue({ data: { acknowledged: true } } as never)
    await ackIncident(7)
    expect(spy).toHaveBeenCalledWith('/plc/incidents/7/ack')
  })
})
