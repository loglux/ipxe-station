import { useState, useEffect, useCallback, useRef } from 'react'
import DownloadProgressBlock from './DownloadProgressBlock'
import './KasperskySection.css'

const POLL_MS = 1500

async function api(path, options) {
  const response = await fetch(path, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.join('; ') : data.detail
    throw new Error(detail || `Server answered ${response.status}`)
  }
  return data
}

function sizeLabel(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${(bytes / 1e6).toFixed(1)} MB`
}

/** Runs a server-side job and polls it until it finishes. */
function useJob(pollPath, onFinished) {
  const [job, setJob] = useState(null)
  const timer = useRef(null)

  const stop = () => {
    if (timer.current) clearInterval(timer.current)
    timer.current = null
  }

  useEffect(() => stop, [])

  const watch = useCallback(() => {
    stop()
    timer.current = setInterval(async () => {
      try {
        const data = await api(pollPath)
        setJob(data)
        if (data.state !== 'running') {
          stop()
          if (onFinished) onFinished(data)
        }
      } catch {
        /* the next tick tries again */
      }
    }, POLL_MS)
  }, [pollPath, onFinished])

  const start = useCallback(
    async (path, body) => {
      setJob({ state: 'running', done: 0, total: 0 })
      try {
        await api(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body || {}),
        })
        watch()
      } catch (err) {
        setJob({ state: 'error', error: err.message })
      }
    },
    [watch],
  )

  return { job, start }
}

function JobResult({ job, describe }) {
  if (!job) return null
  if (job.state === 'error') {
    return (
      <div className="tool-error" role="alert">
        {job.error}
      </div>
    )
  }
  if (job.state === 'done') {
    return (
      <div className="download-status" role="status">
        {describe(job.result)}
      </div>
    )
  }
  return null
}

function progressOf(job) {
  const total = job?.total || 0
  const done = job?.done || 0
  return { downloaded: done, total, percentage: total ? Math.min(100, Math.round((done / total) * 100)) : 0 }
}

function BasesCard({ folder, onChanged }) {
  const [status, setStatus] = useState(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')

  const check = useCallback(async () => {
    setChecking(true)
    setError('')
    try {
      setStatus(await api(`/api/kaspersky/${folder.name}/bases`))
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(false)
    }
  }, [folder.name])

  useEffect(() => {
    check()
  }, [check])

  const { job, start } = useJob(`/api/kaspersky/${folder.name}/jobs/bases`, () => {
    check()
    if (onChanged) onChanged()
  })
  const running = job?.state === 'running'

  const update = () => {
    const ok = window.confirm(
      'Replace the antivirus databases?\n\nDo not do this while a machine is running Kaspersky ' +
        'from the network: it reads this file while it works. A backup of the old databases is kept.',
    )
    if (ok) start(`/api/kaspersky/${folder.name}/bases/update`, {})
  }

  return (
    <div className="krd-block">
      <h5>Antivirus databases</h5>
      <p className="tool-note">
        On the disk: <strong>{folder.bases_label || 'unknown'}</strong>
        {status?.remote_label && (
          <>
            {' '}
            · published by Kaspersky: <strong>{status.remote_label}</strong>
          </>
        )}
      </p>
      {status?.up_to_date === true && <span className="file-badge">✓ up to date</span>}
      {status?.up_to_date === false && <span className="file-badge krd-outdated">newer databases available</span>}
      {(error || status?.error) && (
        <div className="tool-warning" role="note">
          {error || status.error}
        </div>
      )}
      {running && (
        <DownloadProgressBlock
          title="Kaspersky databases"
          progress={progressOf(job)}
          tone="success"
          unit="MB"
          divisor={1024 * 1024}
          decimals={0}
        />
      )}
      <JobResult job={job} describe={(r) => r.message} />
      <div className="download-picker-actions">
        <button className="btn btn-secondary" onClick={check} disabled={checking || running}>
          {checking ? 'Checking…' : 'Check for updates'}
        </button>
        <button className="btn btn-primary" onClick={update} disabled={running || status?.up_to_date === true}>
          {running ? '⏳ Updating…' : '⬇️ Update databases'}
        </button>
      </div>
      <p className="tool-note">
        Downloaded from Kaspersky and checked against its published SHA-512; a file that does not match is
        discarded.
      </p>
    </div>
  )
}

const CATEGORY_ORDER = ['wifi', 'bluetooth', 'graphics', 'ethernet', 'audio', 'storage', 'other']
const MODES = [
  ['none', 'None', 'Only what the disk shipped with.'],
  ['selected', 'Selected devices', 'A small archive with just the devices you tick.'],
  ['full', 'Everything', 'The complete official set, for any machine.'],
]

/** Firmware for the devices of the machines you boot: none, the ones you pick, or everything. */
function FirmwareCard({ folder, onChanged }) {
  const [info, setInfo] = useState(null)
  const [source, setSource] = useState(null)
  const [reports, setReports] = useState({ reports: [], recommended: [] })
  const [mode, setMode] = useState(null)
  const [chosen, setChosen] = useState({})
  const [query, setQuery] = useState('')
  const [dmesg, setDmesg] = useState('')
  const [extras, setExtras] = useState([])
  const [scanned, setScanned] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [disk, src, rep] = await Promise.all([
        api(`/api/kaspersky/${folder.name}/firmware`),
        api('/api/kaspersky/firmware-source'),
        api('/api/kaspersky/firmware-reports'),
      ])
      setInfo(disk)
      setSource(src)
      setReports(rep)
    } catch (err) {
      setError(err.message)
    }
  }, [folder.name])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api(`/api/kaspersky/${folder.name}/firmware`),
      api('/api/kaspersky/firmware-source'),
      api('/api/kaspersky/firmware-reports'),
    ])
      .then(([disk, src, rep]) => {
        if (cancelled) return
        setInfo(disk)
        setSource(src)
        setReports(rep)
        setMode(disk.kind === 'full' ? 'full' : disk.kind === 'custom' ? 'selected' : 'none')
        // building replaces the archive, so start from what is already in it
        setChosen(Object.fromEntries((disk.installed_items || []).map((id) => [id, true])))
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [folder.name])

  const afterJob = useCallback(() => {
    refresh()
    if (onChanged) onChanged()
  }, [refresh, onChanged])
  const { job, start } = useJob(`/api/kaspersky/${folder.name}/jobs/firmware`, afterJob)
  const { job: sourceJob, start: startSource } = useJob('/api/kaspersky/firmware-source/job', afterJob)
  const running = job?.state === 'running' || sourceJob?.state === 'running'

  const catalog = source?.catalog || []
  const picked = catalog.filter((i) => chosen[i.id])
  const pickedBytes = picked.reduce((sum, i) => sum + i.size, 0)
  const large = source && pickedBytes > source.large_bytes

  const needle = query.trim().toLowerCase()
  const visible = catalog.filter(
    (i) => !needle || i.name.toLowerCase().includes(needle) || (i.description || '').toLowerCase().includes(needle),
  )
  const groups = CATEGORY_ORDER.map((key) => ({
    key,
    label: source?.categories?.[key] || key,
    items: visible.filter((i) => i.category === key),
  })).filter((g) => g.items.length > 0)

  const tick = (ids) => setChosen((c) => ({ ...c, ...Object.fromEntries(ids.map((id) => [id, true])) }))

  const useRecommended = () => {
    tick(reports.recommended)
    setMode('selected')
  }

  const scan = async () => {
    setError('')
    try {
      const data = await api(`/api/kaspersky/${folder.name}/firmware/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: dmesg }),
      })
      setExtras(data.missing)
      tick(data.items)
      setScanned(true)
      setMode('selected')
    } catch (err) {
      setError(err.message)
    }
  }

  const build = () =>
    start(`/api/kaspersky/${folder.name}/firmware/custom`, {
      items: picked.map((i) => i.id),
      files: extras.map((m) => ({ name: m.name, alternatives: m.alternatives })),
    })

  const full = () => {
    const ok = window.confirm(
      `Put the complete firmware set (about ${source?.download_mb || 436} MB) on the disk?\n\nEvery machine then ` +
        'fetches it at start, needs at least 4 GB of RAM and takes a few minutes longer to boot. It replaces ' +
        'the small archive, if there is one.',
    )
    if (ok) start(`/api/kaspersky/${folder.name}/firmware/full`, {})
  }

  const remove = async () => {
    if (!window.confirm('Remove the firmware archive from this disk?')) return
    try {
      await api(`/api/kaspersky/${folder.name}/firmware`, { method: 'DELETE' })
      await refresh()
      if (onChanged) onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const clearReports = async () => {
    try {
      await api('/api/kaspersky/firmware-reports', { method: 'DELETE' })
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!info || !source) return error ? <div className="tool-error">{error}</div> : null

  const command =
    `dmesg > /tmp/d.txt; wget -qO- --post-file=/tmp/d.txt ` +
    `http://${window.location.host}/api/kaspersky/${folder.name}/firmware/report`
  const haveReports = reports.reports.length > 0

  return (
    <div className="krd-block">
      <h5>Firmware for Wi-Fi, Bluetooth and other devices</h5>
      <p className="tool-note">
        {info.kind === 'none' && 'No firmware on this disk: the Wi-Fi and Bluetooth of many laptops will not work.'}
        {info.kind === 'custom' && 'A small archive with the devices you chose is installed.'}
        {info.kind === 'full' && 'The complete firmware set is installed.'}{' '}
        {info.archives.map((a) => `${a.name} (${sizeLabel(a.size)})`).join(', ')}
      </p>

      <div className="krd-modes" role="radiogroup" aria-label="Firmware mode">
        {MODES.map(([value, label, hint]) => (
          <label key={value} className="krd-check">
            <input
              type="radio"
              name={`fw-mode-${folder.name}`}
              checked={mode === value}
              onChange={() => setMode(value)}
              disabled={running}
            />
            <span>
              {label}
              <small className="text-muted"> — {hint}</small>
            </span>
          </label>
        ))}
      </div>

      {haveReports && (
        <div className="krd-reports">
          <strong>Machines reported missing firmware</strong>
          <ul>
            {reports.reports.map((r) => (
              <li key={r.mac || r.client}>
                {r.device || r.client}{' '}
                <span className="text-muted">
                  ({r.at}):{' '}
                  {r.missing.length ? r.missing.map((m) => m.name).join(', ') : 'nothing missing'}
                </span>
              </li>
            ))}
          </ul>
          <div className="download-picker-actions">
            <button
              className="btn btn-secondary"
              onClick={useRecommended}
              disabled={running || reports.recommended.length === 0 || !source.downloaded}
            >
              Select what they need ({reports.recommended.length})
            </button>
            <button className="btn btn-secondary btn-small" onClick={clearReports} disabled={running}>
              Clear
            </button>
          </div>
          {!source.downloaded && reports.recommended.length === 0 && (
            <p className="tool-note">Download the firmware release below to match these to devices.</p>
          )}
        </div>
      )}

      {(mode === 'selected' || mode === 'full') && !source.downloaded && (
        <div className="krd-source">
          <p className="tool-note">
            The device list comes from the official linux-firmware release {source.tag} (about {source.download_mb}{' '}
            MB). It is downloaded once, kept on this server, never sent to the machines, and checked against
            kernel.org&apos;s checksum.
          </p>
          {sourceJob?.state === 'running' && (
            <DownloadProgressBlock
              title="linux-firmware"
              progress={progressOf(sourceJob)}
              tone="success"
              unit="MB"
              divisor={1024 * 1024}
              decimals={0}
            />
          )}
          <JobResult job={sourceJob} describe={(r) => `Downloaded and verified: ${r.items} devices.`} />
          <button
            className="btn btn-primary"
            onClick={() => startSource('/api/kaspersky/firmware-source/download', {})}
            disabled={running}
          >
            {sourceJob?.state === 'running' ? '⏳ Downloading…' : `⬇️ Download release (${source.download_mb} MB)`}
          </button>
        </div>
      )}

      {mode === 'selected' && source.downloaded && (
        <div className="krd-catalog">
          <input
            type="search"
            aria-label="Search devices"
            placeholder="Search devices, e.g. AX211, Realtek, Bluetooth"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {groups.length === 0 && <p className="tool-note">Nothing matches.</p>}
          {groups.map((g) => {
            const count = g.items.filter((i) => chosen[i.id]).length
            return (
              <details key={g.key} open={!!needle || count > 0 || g.key === 'wifi'}>
                <summary>
                  {g.label} <span className="text-muted">({g.items.length})</span>
                  {count > 0 && <span className="file-badge">{count} selected</span>}
                </summary>
                {g.items.map((i) => (
                  <label key={i.id} className="krd-check">
                    <input
                      type="checkbox"
                      checked={!!chosen[i.id]}
                      onChange={(e) => setChosen((c) => ({ ...c, [i.id]: e.target.checked }))}
                      disabled={running}
                    />
                    <span>
                      {i.name}
                      <small className="text-muted"> — {sizeLabel(i.size)}</small>
                    </span>
                  </label>
                ))}
              </details>
            )
          })}

          <details className="krd-scan">
            <summary>Something else? Paste the output of dmesg from a machine</summary>
            <textarea
              aria-label="dmesg output"
              value={dmesg}
              onChange={(e) => setDmesg(e.target.value)}
              rows={4}
              placeholder="dmesg | grep -iE 'firmware|failed to load'"
              disabled={running}
            />
            <button className="btn btn-secondary" onClick={scan} disabled={!dmesg.trim() || running}>
              Find missing firmware
            </button>
            {scanned && (
              <p className="tool-note">
                {extras.length === 0
                  ? 'No missing firmware found in that text.'
                  : `Found: ${extras.map((m) => m.name).join(', ')}. The matching devices are ticked.`}
              </p>
            )}
            <p className="tool-note">
              Or let the machines tell the server themselves: turn on the boot script under <em>Screen</em> below.
              To send it by hand from a machine:
              <code className="krd-command">{command}</code>
            </p>
          </details>

          <p className="tool-note" role="status">
            {picked.length === 0 && extras.length === 0
              ? 'Nothing selected.'
              : `${picked.length} device(s) selected, ${sizeLabel(pickedBytes)} unpacked.`}
          </p>
          {large && (
            <div className="tool-warning" role="note">
              That is a lot of firmware. Every machine unpacks it in memory at start; if you need this much,
              &quot;Everything&quot; is simpler.
            </div>
          )}
        </div>
      )}

      {running && job?.state === 'running' && (
        <DownloadProgressBlock
          title="Firmware"
          progress={progressOf(job)}
          tone="success"
          unit="MB"
          divisor={1024 * 1024}
          decimals={0}
        />
      )}
      {error && (
        <div className="tool-error" role="alert">
          {error}
        </div>
      )}
      <JobResult
        job={job}
        describe={(r) =>
          r.added
            ? `Archive built: ${r.added.length} file(s), ${sizeLabel(r.size)}.` +
              (r.skipped.length ? ` Not in the release, skipped: ${r.skipped.join(', ')}.` : '')
            : `Installed ${r.archive} (${sizeLabel(r.size)}).`
        }
      />

      <div className="download-picker-actions">
        {mode === 'selected' && (
          <button
            className="btn btn-primary"
            onClick={build}
            disabled={running || !source.downloaded || (picked.length === 0 && extras.length === 0)}
          >
            {job?.state === 'running' ? '⏳ Working…' : '🔧 Build archive'}
          </button>
        )}
        {mode === 'full' && (
          <button className="btn btn-primary" onClick={full} disabled={running}>
            {job?.state === 'running' ? '⏳ Working…' : `Install everything (${source.download_mb} MB)`}
          </button>
        )}
        {mode === 'none' && info.archives.length > 0 && (
          <button className="btn btn-primary" onClick={remove} disabled={running}>
            Remove firmware from the disk
          </button>
        )}
        {mode !== 'none' && info.archives.length > 0 && (
          <button className="btn btn-secondary" onClick={remove} disabled={running}>
            Remove
          </button>
        )}
        {source.downloaded && (
          <button
            className="btn btn-secondary btn-small"
            onClick={async () => {
              if (!window.confirm('Delete the downloaded release from the server? It is downloaded again when needed.')) return
              await api('/api/kaspersky/firmware-source', { method: 'DELETE' })
              refresh()
            }}
            disabled={running}
          >
            Delete downloaded release ({sizeLabel(source.size)})
          </button>
        )}
      </div>
      <p className="tool-note">
        Firmware is loaded at start, and only on machines with at least {info.min_ram_gb} GB of RAM. Files come from
        linux-firmware {info.tag}, which matches the kernel of Kaspersky Rescue Disk 24.
      </p>
    </div>
  )
}

const SCALE_CHOICES = [
  ['auto', 'Automatic (from the screen)'],
  ['off', 'Do not change'],
  ['1.25', '125%'],
  ['1.5', '150%'],
  ['1.75', '175%'],
  ['2', '200%'],
  ['2.5', '250%'],
]

function ScaleSelect({ id, value, onChange, disabled }) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
      {SCALE_CHOICES.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  )
}

/** Text size and video mode of the disk's desktop: decided here, applied when a machine boots. */
function DisplayCard() {
  const [settings, setSettings] = useState(null)
  const [menu, setMenu] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    api('/api/kaspersky/display')
      .then((data) => {
        if (cancelled) return
        setSettings({ default: data.default, rules: data.rules, report_firmware: data.report_firmware })
        setMenu(data.menu)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const save = async () => {
    setBusy(true)
    setError('')
    setSaved('')
    try {
      await api('/api/kaspersky/display', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          default: settings.default,
          report_firmware: settings.report_firmware,
          // a rule with nothing filled in has nothing to match; drop it, and drop empty fields
          rules: settings.rules
            .map((r) => ({
              ...r,
              match: Object.fromEntries(Object.entries(r.match).filter(([, v]) => v && v.trim())),
            }))
            .filter((r) => Object.keys(r.match).length > 0),
        }),
      })
      setSaved('Saved. Machines pick this up the next time they start Kaspersky.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const changeMenu = async (change) => {
    setBusy(true)
    setError('')
    try {
      const data = await api('/api/kaspersky/display/menu', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(change),
      })
      setMenu(data.menu)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const setRule = (index, patch) =>
    setSettings((s) => ({ ...s, rules: s.rules.map((r, i) => (i === index ? { ...r, ...patch } : r)) }))

  const setRuleMatch = (index, field, value) =>
    setSettings((s) => ({
      ...s,
      rules: s.rules.map((r, i) => {
        if (i !== index) return r
        const match = { ...r.match }
        if (value) match[field] = value
        else delete match[field]
        return { ...r, match }
      }),
    }))

  if (!settings) return error ? <div className="tool-error">{error}</div> : null

  const hasEntries = menu && menu.entries.length > 0

  return (
    <div className="download-subsection tool-card krd-display">
      <h4>🖥️ Screen: text size and resolution</h4>
      <p className="tool-note">
        The disk shows text at a size meant for small screens, which is tiny on a 15 inch laptop with a sharp panel.
        The size is decided here and applied when a machine starts the disk.
      </p>

      <div className="krd-row">
        <label htmlFor="krd-scale-default">Text size</label>
        <ScaleSelect
          id="krd-scale-default"
          value={settings.default}
          onChange={(v) => setSettings((s) => ({ ...s, default: v }))}
          disabled={busy}
        />
      </div>
      <p className="tool-note">
        Automatic reads the size of the laptop&apos;s panel and picks a size that is comfortable to read. Rules below
        override it for particular models.
      </p>

      {settings.rules.length > 0 && <strong>Rules for particular machines</strong>}
      {settings.rules.map((rule, index) => (
        <div key={index} className="krd-rule">
          <input
            aria-label={`Brand of rule ${index + 1}`}
            placeholder="Brand, e.g. Dell*"
            value={rule.match.manufacturer || ''}
            onChange={(e) => setRuleMatch(index, 'manufacturer', e.target.value)}
          />
          <input
            aria-label={`Model of rule ${index + 1}`}
            placeholder="Model, e.g. Latitude 5530"
            value={rule.match.product || ''}
            onChange={(e) => setRuleMatch(index, 'product', e.target.value)}
          />
          <ScaleSelect
            id={`krd-rule-scale-${index}`}
            value={rule.scale}
            onChange={(v) => setRule(index, { scale: v })}
            disabled={busy}
          />
          <button
            className="btn btn-secondary btn-small"
            aria-label={`Remove rule ${index + 1}`}
            onClick={() => setSettings((s) => ({ ...s, rules: s.rules.filter((_, i) => i !== index) }))}
          >
            ✕
          </button>
        </div>
      ))}

      <label className="krd-check">
        <input
          type="checkbox"
          checked={settings.report_firmware}
          onChange={(e) => setSettings((s) => ({ ...s, report_firmware: e.target.checked }))}
          disabled={busy}
        />
        <span>
          Machines tell the server which firmware they could not find
          <small className="text-muted"> — used for the recommendations under Firmware</small>
        </span>
      </label>

      <div className="download-picker-actions">
        <button
          className="btn btn-secondary"
          onClick={() =>
            setSettings((s) => ({ ...s, rules: [...s.rules, { title: '', match: { product: '' }, scale: '1.5' }] }))
          }
          disabled={busy}
        >
          + Add rule
        </button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>
          Save
        </button>
      </div>
      {saved && (
        <div className="download-status" role="status">
          {saved}
        </div>
      )}
      {error && (
        <div className="tool-error" role="alert">
          {error}
        </div>
      )}

      <div className="krd-block">
        <h5>In the boot menu</h5>
        {!hasEntries && (
          <p className="tool-note">
            No Kaspersky Rescue Disk 24 entry in the menu yet. Add one in the Builder, then come back here.
          </p>
        )}
        {hasEntries && (
          <>
            <p className="tool-note">Entries: {menu.entries.map((e) => e.title || e.name).join(', ')}</p>
            <label className="krd-check">
              <input
                type="checkbox"
                checked={menu.hook}
                onChange={(e) => changeMenu({ hook: e.target.checked })}
                disabled={busy}
              />
              <span>
                Use the server's boot script (text size and firmware reports)
                <small className="text-muted"> — the entries fetch a small script from this server when they start</small>
              </span>
            </label>
            <label className="krd-check">
              <input
                type="checkbox"
                checked={menu.native_video}
                onChange={(e) => changeMenu({ native_video: e.target.checked })}
                disabled={busy}
              />
              <span>
                Use the screen&apos;s own resolution
                <small className="text-muted">
                  {' '}
                  — lets the video driver run (removes <code>nomodeset</code>). If a machine shows a black screen,
                  turn this off.
                </small>
              </span>
            </label>
          </>
        )}
      </div>
    </div>
  )
}

/** Keeps extracted Kaspersky Rescue Disks current: antivirus databases and device firmware. */
export default function KasperskySection({ onChanged }) {
  const [folders, setFolders] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await api('/api/kaspersky')
      setFolders(data.folders || [])
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api('/api/kaspersky')
      .then((data) => {
        if (!cancelled) setFolders(data.folders || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const changed = useCallback(() => {
    load()
    if (onChanged) onChanged()
  }, [load, onChanged])

  if (folders.length === 0 && !error) return null

  return (
    <section className="asset-section krd-section">
      <h3>🛡️ Kaspersky Rescue Disk upkeep</h3>
      <p className="text-sm text-muted download-section-note">
        Keep the antivirus databases current and give the disk the firmware it lacks. Changes are made in the
        disk&apos;s folder and apply the next time a machine starts from it.
      </p>
      {error && (
        <div className="tool-error" role="alert">
          {error}
        </div>
      )}
      {folders.map((folder) => (
        <div key={folder.name} className="download-subsection tool-card">
          <h4>
            🛡️ {folder.name}
            {folder.version && <span className="file-badge">{folder.version}</span>}
          </h4>
          <BasesCard folder={folder} onChanged={changed} />
          <FirmwareCard folder={folder} onChanged={changed} />
        </div>
      ))}
      {folders.length > 0 && <DisplayCard />}
    </section>
  )
}
