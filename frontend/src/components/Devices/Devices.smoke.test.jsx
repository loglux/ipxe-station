import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Devices from './Devices'
import { bootMode, deviceName, deviceSub, formatAge } from './deviceFormat'

const NOW = Date.now() / 1000

const CLIENTS = [
  {
    id: 'aaaa',
    manufacturer: 'Dell Inc.',
    product: 'Latitude 5530',
    sku: '0B06',
    serial: 'DEMO123',
    bios_version: '1.36.0',
    bios_date: '04/27/2026',
    mac: '00:11:22:33:44:55',
    uuid: '4c4c4544-0000-0000-0000-000000000001',
    nic_pci: '8086:1a1e',
    platform: 'efi',
    arch: 'x86_64',
    client_ip: '192.168.10.35',
    boots: 3,
    first_seen_at: NOW - 86400 * 3,
    last_seen_at: NOW - 30,
  },
  {
    id: 'bbbb',
    manufacturer: 'LENOVO',
    product: '20W0001',
    serial: 'LEN999',
    bios_version: 'N32ET80W',
    platform: 'pcbios',
    arch: 'x86_64',
    client_ip: '192.168.10.40',
    boots: 1,
    first_seen_at: NOW - 86400 * 10,
    last_seen_at: NOW - 86400 * 5,
  },
]

function mockClients(payload, ok = true) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ({
    ok,
    status: ok ? 200 : 500,
    async json() {
      return payload
    },
  }))
}

describe('Devices', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('lists the machines that reported themselves', async () => {
    mockClients({ clients: CLIENTS })
    render(<Devices />)

    expect(await screen.findByText('Dell Inc. Latitude 5530')).toBeInTheDocument()
    expect(screen.getByText('LENOVO 20W0001')).toBeInTheDocument()
    expect(screen.getByText('DEMO123')).toBeInTheDocument()
    expect(screen.getByText('1.36.0')).toBeInTheDocument()
    expect(screen.getByText('UEFI x64')).toBeInTheDocument()
    expect(screen.getByText('BIOS x64')).toBeInTheDocument()
  })

  it('marks recently seen machines as active and counts them', async () => {
    mockClients({ clients: CLIENTS })
    render(<Devices />)

    await screen.findByText('Dell Inc. Latitude 5530')
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('5 d ago')).toBeInTheDocument()
  })

  it('filters by search text and by brand', async () => {
    mockClients({ clients: CLIENTS })
    render(<Devices />)
    await screen.findByText('Dell Inc. Latitude 5530')

    fireEvent.change(screen.getByLabelText('Search devices'), { target: { value: 'len999' } })
    expect(screen.queryByText('Dell Inc. Latitude 5530')).not.toBeInTheDocument()
    expect(screen.getByText('LENOVO 20W0001')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search devices'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Filter by brand'), { target: { value: 'Dell Inc.' } })
    expect(screen.queryByText('LENOVO 20W0001')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search devices'), { target: { value: 'nothing-matches' } })
    expect(screen.getByText('No device matches the filter.')).toBeInTheDocument()
  })

  it('shows all details of a machine when its name is clicked', async () => {
    mockClients({ clients: CLIENTS })
    render(<Devices />)

    fireEvent.click(await screen.findByText('Dell Inc. Latitude 5530'))

    expect(screen.getByText('4c4c4544-0000-0000-0000-000000000001')).toBeInTheDocument()
    expect(screen.getByText('UUID')).toBeInTheDocument()
    expect(screen.getByText('BIOS date')).toBeInTheDocument()
  })

  it('explains how a device appears when the list is empty', async () => {
    mockClients({ clients: [] })
    render(<Devices />)

    expect(await screen.findByText('No devices yet.')).toBeInTheDocument()
  })

  it('reports a failed request instead of crashing', async () => {
    mockClients({}, false)
    render(<Devices />)

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not load devices'))
  })
})

describe('Devices helpers', () => {
  it('builds readable names and boot modes', () => {
    expect(deviceName({ manufacturer: 'HP', product: 'EliteBook 840' })).toBe('HP EliteBook 840')
    expect(deviceName({ manufacturer: 'HP', product: 'HP EliteBook 840 G9' })).toBe('HP EliteBook 840 G9')
    expect(deviceName({ manufacturer: 'Dell Inc.', product: 'Latitude 5530' })).toBe('Dell Inc. Latitude 5530')
    expect(
      deviceName({ manufacturer: 'LENOVO', product: '21AH00E3UK', family: 'ThinkPad T14 Gen 3' }),
    ).toBe('LENOVO ThinkPad T14 Gen 3')
    expect(deviceSub({ manufacturer: 'LENOVO', product: '21AH00E3UK', family: 'ThinkPad T14 Gen 3' })).toBe(
      'Type 21AH00E3UK',
    )
    expect(deviceSub({ manufacturer: 'Dell Inc.', product: 'Latitude 5530', sku: '0B06' })).toBe('SKU 0B06')
    expect(deviceName({})).toBe('Unknown machine')
    expect(bootMode({ platform: 'efi', arch: 'x86_64' })).toBe('UEFI x64')
    expect(bootMode({})).toBe('')
    expect(formatAge(20)).toBe('just now')
    expect(formatAge(7200)).toBe('2 h ago')
  })
})
