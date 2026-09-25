import { useState, useEffect, useMemo, useCallback } from 'react'
import './Devices.css'
import { DAY_S, bootMode, deviceName, deviceSub, formatAge } from './deviceFormat'

const POLL_MS = 5000
const ONLINE_WINDOW_S = 300

const SORTS = [
  { value: 'last_seen', label: 'Last seen' },
  { value: 'first_seen', label: 'First seen' },
  { value: 'name', label: 'Model' },
  { value: 'boots', label: 'Most boots' },
]

const SEARCH_FIELDS = [
  'manufacturer', 'product', 'sku', 'family', 'serial', 'asset', 'uuid', 'mac',
  'client_ip', 'bios_version', 'nic_pci', 'chip',
]

function formatDateTime(epochSeconds) {
  if (!epochSeconds) return '—'
  return new Date(epochSeconds * 1000).toLocaleString()
}

function matchesQuery(device, query) {
  if (!query) return true
  const needle = query.trim().toLowerCase()
  return SEARCH_FIELDS.some((field) => String(device[field] || '').toLowerCase().includes(needle))
}

function sortDevices(devices, sortKey) {
  const list = [...devices]
  const by = {
    last_seen: (a, b) => (b.last_seen_at || 0) - (a.last_seen_at || 0),
    first_seen: (a, b) => (b.first_seen_at || 0) - (a.first_seen_at || 0),
    name: (a, b) => deviceName(a).localeCompare(deviceName(b)),
    boots: (a, b) => (b.boots || 0) - (a.boots || 0),
  }
  return list.sort(by[sortKey] || by.last_seen)
}

function DeviceDetails({ device }) {
  const rows = [
    ['Brand', device.manufacturer],
    ['Model', device.product],
    ['SKU / product number', device.sku],
    ['Family', device.family],
    ['Serial number', device.serial],
    ['Asset tag', device.asset],
    ['UUID', device.uuid],
    ['MAC address', device.mac],
    ['Last IP address', device.client_ip],
    ['BIOS version', device.bios_version],
    ['BIOS date', device.bios_date],
    ['Network card (PCI id)', device.nic_pci],
    ['Network driver in iPXE', device.chip],
    ['Boot mode', bootMode(device)],
    ['iPXE version', device.ipxe],
    ['First seen', formatDateTime(device.first_seen_at)],
    ['Last seen', formatDateTime(device.last_seen_at)],
    ['Network boots', device.boots],
  ]
  return (
    <dl className="device-details">
      {rows.map(([label, value]) => (
        <div key={label} className="device-detail">
          <dt>{label}</dt>
          <dd>{value === undefined || value === null || value === '' ? '—' : String(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function Devices() {
  const [devices, setDevices] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [manufacturer, setManufacturer] = useState('all')
  const [sortKey, setSortKey] = useState('last_seen')
  const [expandedId, setExpandedId] = useState(null)
  const [now, setNow] = useState(() => Date.now() / 1000)

  const loadDevices = useCallback(async () => {
    try {
      const response = await fetch('/api/monitoring/clients')
      if (!response.ok) throw new Error(`Server answered ${response.status}`)
      const data = await response.json()
      setDevices(data.clients || [])
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load devices')
    } finally {
      setLoaded(true)
      setNow(Date.now() / 1000)
    }
  }, [])

  useEffect(() => {
    loadDevices()
    const timer = setInterval(loadDevices, POLL_MS)
    return () => clearInterval(timer)
  }, [loadDevices])

  const manufacturers = useMemo(
    () => [...new Set(devices.map((d) => d.manufacturer).filter(Boolean))].sort(),
    [devices],
  )

  const visible = useMemo(() => {
    const filtered = devices.filter(
      (d) => (manufacturer === 'all' || d.manufacturer === manufacturer) && matchesQuery(d, query),
    )
    return sortDevices(filtered, sortKey)
  }, [devices, manufacturer, query, sortKey])

  const summary = useMemo(() => {
    const models = new Set(devices.map((d) => deviceName(d)))
    return {
      total: devices.length,
      models: models.size,
      recent: devices.filter((d) => now - (d.last_seen_at || 0) < DAY_S).length,
      online: devices.filter((d) => now - (d.last_seen_at || 0) < ONLINE_WINDOW_S).length,
    }
  }, [devices, now])

  return (
    <div className="devices">
      <div className="devices-header">
        <div>
          <h2>Devices</h2>
          <p className="devices-subtitle">
            Machines that reported themselves when they booted from the network. A machine appears here
            after it reaches the iPXE menu once.
          </p>
        </div>
        <button className="btn btn-sm btn-secondary" onClick={loadDevices} title="Reload the list">
          🔄 Refresh
        </button>
      </div>

      <div className="devices-summary">
        <div className="devices-tile"><strong>{summary.total}</strong><span>Devices</span></div>
        <div className="devices-tile"><strong>{summary.models}</strong><span>Models</span></div>
        <div className="devices-tile"><strong>{summary.recent}</strong><span>Seen in 24 h</span></div>
        <div className="devices-tile"><strong>{summary.online}</strong><span>Active now</span></div>
      </div>

      <div className="devices-toolbar">
        <input
          type="search"
          className="devices-search"
          placeholder="Search model, serial, MAC, IP, BIOS…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search devices"
        />
        <select
          value={manufacturer}
          onChange={(e) => setManufacturer(e.target.value)}
          aria-label="Filter by brand"
        >
          <option value="all">All brands</option>
          {manufacturers.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        <select value={sortKey} onChange={(e) => setSortKey(e.target.value)} aria-label="Sort by">
          {SORTS.map((sort) => (
            <option key={sort.value} value={sort.value}>Sort: {sort.label}</option>
          ))}
        </select>
      </div>

      {error && <div className="devices-error" role="alert">Could not load devices: {error}</div>}

      {loaded && !error && devices.length === 0 && (
        <div className="devices-empty">
          <strong>No devices yet.</strong>
          <span>
            Boot a machine from the network and open the iPXE menu: its brand, model, serial number, BIOS
            version and network card will show up here.
          </span>
        </div>
      )}

      {devices.length > 0 && (
        <div className="devices-table-wrap">
          <table className="devices-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Device</th>
                <th>Serial</th>
                <th>BIOS</th>
                <th>Network</th>
                <th>Boot</th>
                <th className="num">Boots</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((device) => {
                const id = device.id || device.mac || device.client_ip
                const age = now - (device.last_seen_at || 0)
                const isOnline = age < ONLINE_WINDOW_S
                const isOpen = expandedId === id
                return (
                  <DeviceRow
                    key={id}
                    device={device}
                    isOpen={isOpen}
                    isOnline={isOnline}
                    age={age}
                    onToggle={() => setExpandedId(isOpen ? null : id)}
                  />
                )
              })}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={7} className="devices-none">No device matches the filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function DeviceRow({ device, isOpen, isOnline, age, onToggle }) {
  return (
    <>
      <tr className={`device-row ${isOpen ? 'open' : ''}`}>
        <td>
          <span className={`device-status ${isOnline ? 'online' : ''}`}>
            <span className="device-dot" aria-hidden="true" />
            {isOnline ? 'Active' : formatAge(age)}
          </span>
        </td>
        <td>
          <button
            className="device-name"
            onClick={onToggle}
            aria-expanded={isOpen}
            title="Show all details"
          >
            {deviceName(device)}
          </button>
          {deviceSub(device) && <div className="device-sub">{deviceSub(device)}</div>}
        </td>
        <td className="mono">{device.serial || '—'}</td>
        <td>
          {device.bios_version || '—'}
          {device.bios_date && <div className="device-sub">{device.bios_date}</div>}
        </td>
        <td>
          <div className="mono">{device.client_ip || '—'}</div>
          <div className="device-sub mono">{device.mac || ''}</div>
        </td>
        <td>
          {bootMode(device) || '—'}
          {device.nic_pci && <div className="device-sub mono">NIC {device.nic_pci}</div>}
        </td>
        <td className="num">{device.boots || 0}</td>
      </tr>
      {isOpen && (
        <tr className="device-details-row">
          <td colSpan={7}>
            <DeviceDetails device={device} />
          </td>
        </tr>
      )}
    </>
  )
}
