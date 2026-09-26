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

const CATALOG = [
  { id: 'ax211', name: 'Wi-Fi 6E AX211 / AX411 (iwlwifi so-a0-gf-a0)', description: 'Alder Lake', category: 'wifi', size: 9_700_000, count: 7 },
  { id: 'ax200', name: 'Wi-Fi 6 AX200 (iwlwifi cc-a0)', description: '', category: 'wifi', size: 9_000_000, count: 7 },
  { id: 'ibt', name: 'Intel Bluetooth (btusb intel ibt-0040-0041)', description: '', category: 'bluetooth', size: 800_000, count: 2 },
  { id: 'amdgpu-navi', name: 'amdgpu — navi10', description: '', category: 'graphics', size: 2_000_000, count: 9 },
  { id: 'huge', name: 'nfp-nic — everything', description: '', category: 'ethernet', size: 300_000_000, count: 9 },
]

const SOURCE = {
  tag: '20230210',
  download_mb: 436,
  downloaded: true,
  size: 436_382_164,
  items: CATALOG.length,
  catalog: CATALOG,
  categories: { wifi: 'Wi-Fi', bluetooth: 'Bluetooth', graphics: 'Graphics', ethernet: 'Network cards', other: 'Everything else' },
  large_bytes: 250 * 1024 * 1024,
}

const DISK_NONE = { archives: [], kind: 'none', tag: '20230210', min_ram_gb: 3.1 }
const NO_REPORTS = { reports: [], recommended: [] }

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
    'GET /api/kaspersky/kaspersky-24/firmware': DISK_NONE,
    'GET /api/kaspersky/firmware-source': SOURCE,
    'GET /api/kaspersky/firmware-reports': NO_REPORTS,
    'POST /api/kaspersky/kaspersky-24/firmware/scan': {
      missing: [{ name: 'iwlwifi-so-a0-gf-a0-72.ucode', alternatives: ['iwlwifi-so-a0-gf-a0-71.ucode'], companions: [] }],
      items: ['ax211'],
    },
    'POST /api/kaspersky/kaspersky-24/firmware/custom': { started: true },
    'POST /api/kaspersky/kaspersky-24/firmware/full': { started: true },
    'POST /api/kaspersky/firmware-source/download': { started: true },
    'POST /api/kaspersky/kaspersky-24/bases/update': { started: true },
    'GET /api/kaspersky/display': {
      default: 'auto',
      report_firmware: true,
      rules: [],
      match_fields: ['manufacturer', 'product'],
      menu: { entries: [{ name: 'kaspersky_1', title: 'Kaspersky 24' }], hook: false, native_video: false },
    },
    'PUT /api/kaspersky/display': { success: true },
    'POST /api/kaspersky/display/menu': {
      menu: { entries: [{ name: 'kaspersky_1', title: 'Kaspersky 24' }], hook: true, native_video: false },
    },
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

const posted = (calls, key) => calls.find((c) => c.key === key)

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

  describe('databases', () => {
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
      await waitFor(() => expect(posted(calls, 'POST /api/kaspersky/kaspersky-24/bases/update')).toBeTruthy())
    })
  })

  describe('firmware', () => {
    const openSelected = async () => {
      render(<KasperskySection />)
      fireEvent.click(await screen.findByLabelText(/Selected devices/))
    }

    it('starts with no firmware and says what that means', async () => {
      mockApi()
      render(<KasperskySection />)
      expect(await screen.findByText(/No firmware on this disk/)).toBeInTheDocument()
      expect(screen.getByLabelText(/None/)).toBeChecked()
    })

    it('opens on the mode that matches what is on the disk', async () => {
      mockApi({
        'GET /api/kaspersky/kaspersky-24/firmware': {
          archives: [{ name: 'linux-firmware-custom.tar.gz', size: 3_300_000 }],
          kind: 'custom',
          tag: '20230210',
          min_ram_gb: 3.1,
        },
      })
      render(<KasperskySection />)
      expect(await screen.findByLabelText(/Selected devices/)).toBeChecked()
      expect(screen.getByText(/linux-firmware-custom.tar.gz \(3.3 MB\)/)).toBeInTheDocument()
    })

    it('starts from the devices already in the installed archive, so building does not drop them', async () => {
      const calls = mockApi({
        'GET /api/kaspersky/kaspersky-24/firmware': {
          archives: [{ name: 'linux-firmware-custom.tar.gz', size: 3_300_000 }],
          kind: 'custom',
          tag: '20230210',
          min_ram_gb: 3.1,
          installed_items: ['ax211', 'ibt'],
        },
      })
      render(<KasperskySection />)
      expect(await screen.findByLabelText(/Wi-Fi 6E AX211/)).toBeChecked()
      expect(screen.getByLabelText(/Intel Bluetooth/)).toBeChecked()
      fireEvent.click(screen.getByLabelText(/amdgpu — navi10/))
      fireEvent.click(screen.getByRole('button', { name: /Build archive/ }))
      await waitFor(() => expect(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/custom')).toBeTruthy())
      const body = JSON.parse(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/custom').body)
      expect(body.items.sort()).toEqual(['amdgpu-navi', 'ax211', 'ibt'])
    })

    it('lists every device by category with its size, ready to tick', async () => {
      mockApi()
      await openSelected()
      expect(await screen.findByText(/Wi-Fi 6E AX211/)).toBeInTheDocument()
      expect(screen.getByText(/Intel Bluetooth/)).toBeInTheDocument()
      expect(screen.getByText('Wi-Fi')).toBeInTheDocument()
      expect(screen.getByText('Bluetooth')).toBeInTheDocument()
      expect(screen.getByText('Nothing selected.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Build archive/ })).toBeDisabled()
    })

    it('builds the archive from the ticked devices', async () => {
      const calls = mockApi()
      await openSelected()
      fireEvent.click(await screen.findByLabelText(/Wi-Fi 6E AX211/))
      fireEvent.click(screen.getByLabelText(/Intel Bluetooth/))
      expect(screen.getByText(/2 device\(s\) selected, 10.5 MB unpacked/)).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: /Build archive/ }))
      await waitFor(() => expect(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/custom')).toBeTruthy())
      const body = JSON.parse(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/custom').body)
      expect(body.items.sort()).toEqual(['ax211', 'ibt'])
      expect(body.files).toEqual([])
    })

    it('searches the list', async () => {
      mockApi()
      await openSelected()
      fireEvent.change(await screen.findByLabelText('Search devices'), { target: { value: 'navi' } })
      expect(screen.getByText(/amdgpu — navi10/)).toBeInTheDocument()
      expect(screen.queryByText(/Wi-Fi 6E AX211/)).not.toBeInTheDocument()
      fireEvent.change(screen.getByLabelText('Search devices'), { target: { value: 'zzz' } })
      expect(screen.getByText('Nothing matches.')).toBeInTheDocument()
    })

    it('warns when the selection is large', async () => {
      mockApi()
      await openSelected()
      fireEvent.click(await screen.findByLabelText(/nfp-nic/))
      expect(screen.getByText(/That is a lot of firmware/)).toBeInTheDocument()
    })

    it('turns a pasted dmesg into ticked devices and the named files', async () => {
      const calls = mockApi()
      await openSelected()
      fireEvent.click(await screen.findByText(/Something else\?/))
      fireEvent.change(screen.getByLabelText('dmesg output'), {
        target: { value: 'iwlwifi: firmware: failed to load iwlwifi-so-a0-gf-a0-72.ucode' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Find missing firmware' }))
      expect(await screen.findByText(/Found: iwlwifi-so-a0-gf-a0-72.ucode/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Wi-Fi 6E AX211/)).toBeChecked()

      fireEvent.click(screen.getByRole('button', { name: /Build archive/ }))
      await waitFor(() => expect(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/custom')).toBeTruthy())
      const body = JSON.parse(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/custom').body)
      expect(body.items).toEqual(['ax211'])
      expect(body.files).toEqual([{ name: 'iwlwifi-so-a0-gf-a0-72.ucode', alternatives: ['iwlwifi-so-a0-gf-a0-71.ucode'] }])
    })

    it('recommends what the machines reported and ticks it on request', async () => {
      mockApi({
        'GET /api/kaspersky/firmware-reports': {
          reports: [
            {
              at: '2026-09-26 21:10:00',
              client: '192.168.10.50',
              mac: 'aa:bb',
              device: 'Dell Inc. Latitude 5530',
              missing: [{ name: 'iwlwifi-so-a0-gf-a0-72.ucode', alternatives: [], companions: [] }],
              items: ['ax211', 'ibt'],
            },
          ],
          recommended: ['ax211', 'ibt'],
        },
      })
      render(<KasperskySection />)
      expect(await screen.findByText(/Dell Inc. Latitude 5530/)).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /Select what they need \(2\)/ }))
      expect(await screen.findByLabelText(/Wi-Fi 6E AX211/)).toBeChecked()
      expect(screen.getByLabelText(/Intel Bluetooth/)).toBeChecked()
      expect(screen.getByLabelText(/Selected devices/)).toBeChecked()
    })

    it('offers to download the release first when the list is not there yet', async () => {
      const calls = mockApi({
        'GET /api/kaspersky/firmware-source': { ...SOURCE, downloaded: false, size: 0, items: 0, catalog: [] },
      })
      await openSelected()
      expect(await screen.findByText(/never sent to the machines/)).toBeInTheDocument()
      expect(screen.queryByLabelText('Search devices')).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /Download release \(436 MB\)/ }))
      await waitFor(() => expect(posted(calls, 'POST /api/kaspersky/firmware-source/download')).toBeTruthy())
    })

    it('installs the complete set after a confirmation', async () => {
      const calls = mockApi()
      const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
      render(<KasperskySection />)
      fireEvent.click(await screen.findByLabelText(/Everything/))
      const button = screen.getByRole('button', { name: /Install everything/ })
      fireEvent.click(button)
      expect(calls.some((c) => c.key.endsWith('/firmware/full'))).toBe(false)
      confirm.mockReturnValue(true)
      fireEvent.click(button)
      await waitFor(() => expect(posted(calls, 'POST /api/kaspersky/kaspersky-24/firmware/full')).toBeTruthy())
    })
  })

  describe('screen settings', () => {
    it('shows the default text size and how the menu is set up', async () => {
      mockApi()
      render(<KasperskySection />)
      expect(await screen.findByLabelText('Text size')).toHaveValue('auto')
      expect(screen.getByText(/Entries: Kaspersky 24/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Use the server's boot script/)).not.toBeChecked()
      expect(screen.getByLabelText(/Use the screen's own resolution/)).not.toBeChecked()
    })

    it('turns the script on in the menu when the box is ticked', async () => {
      const calls = mockApi()
      render(<KasperskySection />)
      fireEvent.click(await screen.findByLabelText(/Use the server's boot script/))
      await waitFor(() => expect(screen.getByLabelText(/Use the server's boot script/)).toBeChecked())
      expect(JSON.parse(posted(calls, 'POST /api/kaspersky/display/menu').body)).toEqual({ hook: true })
    })

    it('saves the default, the reporting choice and a rule, leaving out empty fields', async () => {
      const calls = mockApi()
      render(<KasperskySection />)
      fireEvent.change(await screen.findByLabelText('Text size'), { target: { value: '1.5' } })
      fireEvent.click(screen.getByLabelText(/Machines tell the server/))
      fireEvent.click(screen.getByRole('button', { name: '+ Add rule' }))
      fireEvent.change(screen.getByLabelText('Model of rule 1'), { target: { value: 'Latitude 5530' } })
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(posted(calls, 'PUT /api/kaspersky/display')).toBeTruthy())
      expect(JSON.parse(posted(calls, 'PUT /api/kaspersky/display').body)).toEqual({
        default: '1.5',
        report_firmware: false,
        rules: [{ title: '', match: { product: 'Latitude 5530' }, scale: '1.5' }],
      })
      expect(await screen.findByText(/Saved\./)).toBeInTheDocument()
    })

    it('does not send a rule that has nothing filled in', async () => {
      const calls = mockApi()
      render(<KasperskySection />)
      await screen.findByLabelText('Text size')
      fireEvent.click(screen.getByRole('button', { name: '+ Add rule' }))
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))
      await waitFor(() => expect(posted(calls, 'PUT /api/kaspersky/display')).toBeTruthy())
      expect(JSON.parse(posted(calls, 'PUT /api/kaspersky/display').body).rules).toEqual([])
    })

    it('explains when there is no Kaspersky entry in the menu yet', async () => {
      mockApi({
        'GET /api/kaspersky/display': {
          default: 'auto',
          report_firmware: true,
          rules: [],
          match_fields: [],
          menu: { entries: [], hook: false, native_video: false },
        },
      })
      render(<KasperskySection />)
      expect(await screen.findByText(/No Kaspersky Rescue Disk 24 entry in the menu yet/)).toBeInTheDocument()
    })
  })
})

