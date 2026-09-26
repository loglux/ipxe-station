import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import KasperskySection from './KasperskySection'

const FOLDER = {
  name: 'kaspersky-24',
  version: 'Kaspersky Rescue Disk 24.0.7.0',
  bases: '202509010000',
  bases_label: '2025-09-01 00:00',
  firmware: { kind: 'none' },
}

const PRESETS = [
  { id: 'intel-ax211', name: 'Intel Wi-Fi 6E AX211 / AX411', description: 'Alder and Raptor Lake.', files: [] },
  { id: 'intel-bluetooth', name: 'Intel Bluetooth', description: 'Bluetooth.', files: [] },
]

function json(data, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) })
}

function mockApi(overrides = {}) {
  const calls = []
  const routes = {
    'GET /api/kaspersky': { folders: [FOLDER] },
    'GET /api/kaspersky/kaspersky-24/bases': {
      local: '202509010000',
      remote: '202609261328',
      remote_label: '2026-09-26 13:28',
      up_to_date: false,
      error: '',
    },
    'GET /api/kaspersky/kaspersky-24/firmware': {
      archives: [],
      kind: 'none',
      tag: '20230210',
      min_ram_gb: 3.1,
      presets: PRESETS,
      reports: [],
    },
    'POST /api/kaspersky/kaspersky-24/firmware/scan': {
      missing: [
        { name: 'iwlwifi-so-a0-gf-a0-72.ucode', alternatives: ['iwlwifi-so-a0-gf-a0-71.ucode'], companions: [] },
        { name: 'intel/ibt-0040-0041.sfi', alternatives: [], companions: [] },
      ],
      presets: ['intel-ax211', 'intel-bluetooth'],
    },
    'POST /api/kaspersky/kaspersky-24/firmware/custom': { started: true },
    'POST /api/kaspersky/kaspersky-24/bases/update': { started: true },
    ...overrides,
  }
  vi.stubGlobal(
    'fetch',
    vi.fn((url, options = {}) => {
      const key = `${options.method || 'GET'} ${url}`
      calls.push({ key, body: options.body })
      if (key in routes) return json(routes[key])
      return json({ detail: `unexpected ${key}` }, false)
    }),
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('KasperskySection', () => {
  it('renders nothing when there is no extracted Kaspersky disk', async () => {
    mockApi({ 'GET /api/kaspersky': { folders: [] } })
    const { container } = render(<KasperskySection />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('shows both dates and offers the update', async () => {
    mockApi()
    render(<KasperskySection />)
    expect(await screen.findByText('2025-09-01 00:00')).toBeInTheDocument()
    expect(await screen.findByText('2026-09-26 13:28')).toBeInTheDocument()
    expect(screen.getByText('newer databases available')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Update databases/ })).toBeEnabled()
  })

  it('asks before replacing the databases and starts the update once confirmed', async () => {
    const calls = mockApi()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<KasperskySection />)
    const button = await screen.findByRole('button', { name: /Update databases/ })
    await waitFor(() => expect(button).toBeEnabled())

    fireEvent.click(button)
    expect(confirm).toHaveBeenCalled()
    expect(calls.some((c) => c.key.endsWith('/bases/update'))).toBe(false)

    confirm.mockReturnValue(true)
    fireEvent.click(button)
    await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/kaspersky/kaspersky-24/bases/update')).toBe(true))
  })

  it('turns pasted dmesg into a selection and builds the archive from it', async () => {
    const calls = mockApi()
    render(<KasperskySection />)
    const box = await screen.findByLabelText(/Paste the output of dmesg/)
    fireEvent.change(box, { target: { value: 'iwlwifi: firmware: failed to load iwlwifi-so-a0-gf-a0-72.ucode' } })
    fireEvent.click(screen.getByRole('button', { name: 'Find missing firmware' }))

    expect(await screen.findByText('iwlwifi-so-a0-gf-a0-72.ucode')).toBeInTheDocument()
    expect(screen.getByLabelText(/Intel Wi-Fi 6E AX211/)).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: /Build small archive/ }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/kaspersky/kaspersky-24/firmware/custom')).toBe(true),
    )
    const body = JSON.parse(calls.find((c) => c.key.endsWith('/firmware/custom')).body)
    expect(body.presets.sort()).toEqual(['intel-ax211', 'intel-bluetooth'])
    expect(body.files).toEqual([
      { name: 'iwlwifi-so-a0-gf-a0-72.ucode', alternatives: ['iwlwifi-so-a0-gf-a0-71.ucode'] },
      { name: 'intel/ibt-0040-0041.sfi', alternatives: [] },
    ])
  })

  it('does not offer to build until something is chosen', async () => {
    mockApi()
    render(<KasperskySection />)
    const build = await screen.findByRole('button', { name: /Build small archive/ })
    expect(build).toBeDisabled()
    fireEvent.click(await screen.findByLabelText(/Intel Bluetooth/))
    expect(build).toBeEnabled()
  })
})
