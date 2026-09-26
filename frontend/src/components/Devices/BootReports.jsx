import { useState, useEffect } from 'react'
import { reportChips } from './deviceFormat'

async function api(path, options) {
  const response = await fetch(path, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Server answered ${response.status}`)
  return data
}

const SECTION_LABELS = {
  system: 'System',
  memory: 'Memory',
  cpu: 'Processor',
  dmi: 'Hardware (DMI)',
  disks: 'Disks',
  pci: 'PCI devices and their drivers',
  usb: 'USB devices',
  network: 'Network and radios',
  display: 'Screen',
  power: 'Power and battery',
  'kernel-messages': 'Kernel messages (errors, failures, missing firmware)',
  'failed-units': 'Failed services',
  'journal-errors': 'Errors in the system journal',
}

function ReportDetails({ id }) {
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api(`/api/boot-reports/${id}`)
      .then((data) => {
        if (!cancelled) setReport(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (error) return <div className="devices-error" role="alert">{error}</div>
  if (!report) return <small>Loading…</small>
  const { summary } = report
  return (
    <div className="boot-report-details">
      {summary.missing_firmware?.length > 0 && (
        <p className="boot-report-note">
          <strong>Missing firmware:</strong> {summary.missing_firmware.join(', ')}
        </p>
      )}
      {summary.no_driver?.length > 0 && (
        <div className="boot-report-note">
          <strong>Devices without a driver:</strong>
          <ul>
            {summary.no_driver.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      )}
      {summary.failed_units?.length > 0 && (
        <p className="boot-report-note">
          <strong>Failed services:</strong> {summary.failed_units.join(', ')}
        </p>
      )}
      {Object.entries(report.sections).map(([name, text]) => (
        <details key={name} className="boot-report-section">
          <summary>{SECTION_LABELS[name] || name}</summary>
          <pre>{text || '(empty)'}</pre>
        </details>
      ))}
    </div>
  )
}

function ReportCard({ report, onChanged }) {
  const [open, setOpen] = useState(false)
  const { summary } = report
  const remove = async () => {
    if (!window.confirm('Delete this report?')) return
    try {
      await api(`/api/boot-reports/${report.id}`, { method: 'DELETE' })
      if (onChanged) onChanged()
    } catch {
      /* the list refreshes on its own and shows what is left */
    }
  }
  return (
    <div className="boot-report">
      <div className="boot-report-head">
        <strong>{summary.os || 'Live system'}</strong>
        <span className="device-sub">
          {summary.kernel} · {report.at}
        </span>
      </div>
      <div className="boot-report-chips">
        {reportChips(summary).map((chip) => (
          <span key={chip.text} className={`boot-chip ${chip.bad ? 'bad' : ''}`}>
            {chip.text}
          </span>
        ))}
      </div>
      <div className="boot-report-actions">
        <button className="btn btn-sm btn-secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Hide details' : 'Show details'}
        </button>
        <button className="btn btn-sm btn-secondary" onClick={remove}>
          Delete
        </button>
      </div>
      {open && <ReportDetails id={report.id} />}
    </div>
  )
}

/** What a machine said about itself after it started a live system. */
export function BootReports({ reports, onChanged }) {
  if (!reports || reports.length === 0) return null
  return (
    <div className="boot-reports">
      <h4>Boot reports</h4>
      {reports.map((report) => (
        <ReportCard key={report.id} report={report} onChanged={onChanged} />
      ))}
    </div>
  )
}

/** Which live systems in the menu ask for a boot report. */
export function BootReportSettings() {
  const [entries, setEntries] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    api('/api/boot-reports/entries')
      .then((data) => {
        if (!cancelled) setEntries(data.entries || [])
      })
      .catch(() => {
        /* no menu yet, or an older server: the settings simply stay out of the way */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const toggle = async (name, on) => {
    setBusy(true)
    setError('')
    const enabled = entries.filter((e) => (e.name === name ? on : e.enabled)).map((e) => e.name)
    try {
      const data = await api('/api/boot-reports/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      setEntries(data.entries || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (entries.length === 0) return null
  return (
    <details className="boot-report-settings">
      <summary>Boot reports from live systems</summary>
      <p className="devices-subtitle">
        A live system that is asked to can tell this server how it went: memory, disks, devices and their drivers,
        the battery, kernel errors and missing firmware, failed services. The report is sent about a minute after
        the desktop starts. Serial numbers are not collected. Kaspersky Rescue Disk has its own report, under
        Assets.
      </p>
      {entries.map((entry) => (
        <label key={entry.name} className="boot-report-entry">
          <input
            type="checkbox"
            checked={entry.enabled}
            onChange={(e) => toggle(entry.name, e.target.checked)}
            disabled={busy}
          />
          <span>{entry.title || entry.name}</span>
        </label>
      ))}
      {error && <div className="devices-error" role="alert">{error}</div>}
    </details>
  )
}

