import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Devices from './Devices'
import { BootReports, BootReportSettings } from './BootReports'
import { ramLabel, reportChips } from './deviceFormat'

const SUMMARY = {
  os: 'Debian GNU/Linux 13 (trixie)',
  kernel: '6.12.63+deb13-amd64',
  boot: 'uefi',
  ram_mb: 15745,
  batteries: [{ name: 'BAT0', health_pct: 76 }],
  missing_firmware: ['iwlwifi-so-a0-gf-a0-72.ucode'],
  no_driver: ['Audio device [0403]: Intel Corporation Alder Lake PCH-P High Definition Audio'],
  failed_units: ['bluetooth.service'],
  kernel_problem_lines: 3,
}

const REPORT = { id: 'r1', at: '2026-09-26 23:16:00', mac: 'aa:bb', summary: SUMMARY }

const FULL = {
  ...REPORT,
  sections: { system: 'os=Debian', pci: '00:14.3 Network controller: Intel WiFi', 'kernel-messages': '[3.1] error' },
}

function mockApi(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options = {}) => {
      const key = `${options.method || 'GET'} ${url}`
      calls.push({ key, body: options.body })
      if (key in routes) {
        const answer = routes[key]
        const ok = !(answer && answer.__error)
        return { ok, status: ok ? 200 : 422, json: async () => (ok ? answer : { detail: answer.__error }) }
      }
      return { ok: false, status: 404, json: async () => ({ detail: `unexpected ${key}` }) }
    }),
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('report chips', () => {
  it('turns a summary into facts and problems', () => {
    const chips = reportChips(SUMMARY)
    const text = chips.map((c) => c.text)
    expect(text).toEqual(
      expect.arrayContaining([
        'RAM 15.4 GB',
        'UEFI',
        'Battery 76% of new',
        'Missing firmware: 1',
        'No driver: 1',
        'Failed services: 1',
        'Kernel messages: 3',
      ]),
    )
    expect(chips.find((c) => c.text === 'Missing firmware: 1').bad).toBe(true)
    expect(chips.find((c) => c.text === 'Battery 76% of new').bad).toBe(false)
    expect(text).not.toContain('No problems seen')
  })

  it('flags a worn battery and says so when nothing is wrong', () => {
    expect(reportChips({ batteries: [{ health_pct: 40 }] }).find((c) => c.text.startsWith('Battery')).bad).toBe(true)
    expect(reportChips({ ram_mb: 4096, boot: 'bios', batteries: [] }).map((c) => c.text)).toEqual([
      'RAM 4.0 GB',
      'BIOS',
      'No problems seen',
    ])
  })

  it('formats memory', () => {
    expect(ramLabel(0)).toBe('—')
    expect(ramLabel(512)).toBe('512 MB')
    expect(ramLabel(2048)).toBe('2.0 GB')
  })
})

describe('BootReports', () => {
  it('shows nothing without reports', () => {
    const { container } = render(<BootReports reports={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the system, when it reported, and the chips', () => {
    render(<BootReports reports={[REPORT]} />)
    expect(screen.getByText('Debian GNU/Linux 13 (trixie)')).toBeInTheDocument()
    expect(screen.getByText(/2026-09-26 23:16:00/)).toBeInTheDocument()
    expect(screen.getByText('Missing firmware: 1')).toBeInTheDocument()
  })

  it('loads the full report on request and shows what needs a look first', async () => {
    const calls = mockApi({ 'GET /api/boot-reports/r1': FULL })
    render(<BootReports reports={[REPORT]} />)
    expect(calls).toHaveLength(0) // nothing is fetched until it is asked for
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }))
    expect(await screen.findByText(/iwlwifi-so-a0-gf-a0-72.ucode/)).toBeInTheDocument()
    expect(screen.getByText(/Alder Lake PCH-P High Definition Audio/)).toBeInTheDocument()
    expect(screen.getByText(/bluetooth.service/)).toBeInTheDocument()
    expect(screen.getByText('PCI devices and their drivers')).toBeInTheDocument()
    expect(screen.getByText('Kernel messages (errors, failures, missing firmware)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Hide details' }))
    expect(screen.queryByText('PCI devices and their drivers')).not.toBeInTheDocument()
  })

  it('shows why the details could not be loaded', async () => {
    mockApi({ 'GET /api/boot-reports/r1': { __error: 'No such report' } })
    render(<BootReports reports={[REPORT]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No such report')
  })

  it('deletes only after a confirmation and then tells the list to refresh', async () => {
    const calls = mockApi({ 'DELETE /api/boot-reports/r1': { deleted: true } })
    const changed = vi.fn()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<BootReports reports={[REPORT]} onChanged={changed} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(calls).toHaveLength(0)
    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(changed).toHaveBeenCalled())
    expect(calls[0].key).toBe('DELETE /api/boot-reports/r1')
  })
})

describe('BootReportSettings', () => {
  const ENTRIES = {
    entries: [
      { name: 'debian_live_1', title: 'Debian Live (ISO)', enabled: false },
      { name: 'debian_live_2', title: 'Debian Live (squashfs)', enabled: true },
    ],
  }

  it('stays out of the way when there is no live system in the menu', async () => {
    mockApi({ 'GET /api/boot-reports/entries': { entries: [] } })
    const { container } = render(<BootReportSettings />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('lists the live systems and which ones ask for a report', async () => {
    mockApi({ 'GET /api/boot-reports/entries': ENTRIES })
    render(<BootReportSettings />)
    expect(await screen.findByLabelText('Debian Live (ISO)')).not.toBeChecked()
    expect(screen.getByLabelText('Debian Live (squashfs)')).toBeChecked()
    expect(screen.getByText(/Serial numbers are not collected/)).toBeInTheDocument()
  })

  it('sends the whole choice when one box is ticked', async () => {
    const calls = mockApi({
      'GET /api/boot-reports/entries': ENTRIES,
      'POST /api/boot-reports/entries': {
        entries: [
          { name: 'debian_live_1', title: 'Debian Live (ISO)', enabled: true },
          { name: 'debian_live_2', title: 'Debian Live (squashfs)', enabled: true },
        ],
      },
    })
    render(<BootReportSettings />)
    fireEvent.click(await screen.findByLabelText('Debian Live (ISO)'))
    await waitFor(() => expect(screen.getByLabelText('Debian Live (ISO)')).toBeChecked())
    const post = calls.find((c) => c.key === 'POST /api/boot-reports/entries')
    expect(JSON.parse(post.body).enabled.sort()).toEqual(['debian_live_1', 'debian_live_2'])
  })

  it('shows why a choice was refused', async () => {
    mockApi({
      'GET /api/boot-reports/entries': ENTRIES,
      'POST /api/boot-reports/entries': { __error: 'Menu not valid' },
    })
    render(<BootReportSettings />)
    fireEvent.click(await screen.findByLabelText('Debian Live (ISO)'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Menu not valid')
  })
})

describe('Devices with reports', () => {
  it('shows how many reports a machine has and opens them with its details', async () => {
    mockApi({
      'GET /api/monitoring/clients': {
        clients: [
          {
            id: 'aaaa',
            manufacturer: 'Dell Inc.',
            product: 'Latitude 5530',
            mac: 'aa:bb',
            boots: 2,
            last_seen_at: Date.now() / 1000,
            boot_reports: [REPORT],
          },
        ],
      },
      'GET /api/boot-reports/entries': { entries: [] },
    })
    render(<Devices />)
    expect(await screen.findByText('📋 1 boot report')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Dell Inc. Latitude 5530' }))
    expect(await screen.findByText('Boot reports')).toBeInTheDocument()
    expect(screen.getByText('Debian GNU/Linux 13 (trixie)')).toBeInTheDocument()
  })
})
