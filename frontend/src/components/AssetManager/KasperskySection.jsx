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
function useJob(folder, kind, onFinished) {
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
        const data = await api(`/api/kaspersky/${folder}/jobs/${kind}`)
        setJob(data)
        if (data.state !== 'running') {
          stop()
          if (onFinished) onFinished(data)
        }
      } catch {
        /* the next tick tries again */
      }
    }, POLL_MS)
  }, [folder, kind, onFinished])

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

  const { job, start } = useJob(folder.name, 'bases', () => {
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

function FirmwareCard({ folder, onChanged }) {
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [presets, setPresets] = useState({})
  const [dmesg, setDmesg] = useState('')
  const [missing, setMissing] = useState([])
  const [picked, setPicked] = useState({})
  const [scanned, setScanned] = useState(false)

  const load = useCallback(async () => {
    try {
      setInfo(await api(`/api/kaspersky/${folder.name}/firmware`))
    } catch (err) {
      setError(err.message)
    }
  }, [folder.name])

  useEffect(() => {
    let cancelled = false
    api(`/api/kaspersky/${folder.name}/firmware`)
      .then((data) => {
        if (!cancelled) setInfo(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [folder.name])

  const { job, start } = useJob(folder.name, 'firmware', () => {
    load()
    if (onChanged) onChanged()
  })
  const running = job?.state === 'running'

  const applyMissing = (list, presetIds = []) => {
    setMissing(list)
    setPicked(Object.fromEntries(list.map((m) => [m.name, true])))
    setPresets((p) => ({ ...p, ...Object.fromEntries(presetIds.map((id) => [id, true])) }))
    setScanned(true)
  }

  const scan = async () => {
    setError('')
    try {
      const data = await api(`/api/kaspersky/${folder.name}/firmware/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: dmesg }),
      })
      applyMissing(data.missing, data.presets)
    } catch (err) {
      setError(err.message)
    }
  }

  const build = () =>
    start(`/api/kaspersky/${folder.name}/firmware/custom`, {
      presets: Object.keys(presets).filter((id) => presets[id]),
      files: missing
        .filter((m) => picked[m.name])
        .map((m) => ({ name: m.name, alternatives: m.alternatives })),
    })

  const full = () => {
    if (
      window.confirm(
        'Download the complete firmware set (about 436 MB)?\n\nMachines then need at least 4 GB of RAM ' +
          'and take a few minutes longer to start. It replaces the small archive, if there is one.',
      )
    ) {
      start(`/api/kaspersky/${folder.name}/firmware/full`, {})
    }
  }

  const remove = async () => {
    if (!window.confirm('Remove the firmware archive from this disk?')) return
    try {
      await api(`/api/kaspersky/${folder.name}/firmware`, { method: 'DELETE' })
      await load()
      if (onChanged) onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!info) return error ? <div className="tool-error">{error}</div> : null

  const nothingChosen = !Object.values(presets).some(Boolean) && !missing.some((m) => picked[m.name])
  const command =
    `dmesg > /tmp/d.txt; wget -qO- --post-file=/tmp/d.txt ` +
    `http://${window.location.host}/api/kaspersky/${folder.name}/firmware/report`

  return (
    <div className="krd-block">
      <h5>Firmware for Wi-Fi, Bluetooth and other devices</h5>
      <p className="tool-note">
        {info.kind === 'none' && 'No firmware on this disk: the Wi-Fi and Bluetooth of many laptops will not work.'}
        {info.kind === 'custom' && 'A small archive with the files you chose is installed.'}
        {info.kind === 'full' && 'The complete firmware set is installed.'}{' '}
        {info.archives.map((a) => `${a.name} (${sizeLabel(a.size)})`).join(', ')}
      </p>
      <p className="tool-note">
        Firmware is loaded at start, and only on machines with at least {info.min_ram_gb} GB of RAM.
      </p>

      <fieldset className="krd-presets">
        <legend>Devices</legend>
        {info.presets.map((p) => (
          <label key={p.id} className="krd-check">
            <input
              type="checkbox"
              checked={!!presets[p.id]}
              onChange={(e) => setPresets((s) => ({ ...s, [p.id]: e.target.checked }))}
              disabled={running}
            />
            <span>
              {p.name}
              <small className="text-muted"> — {p.description}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="krd-scan">
        <label htmlFor={`dmesg-${folder.name}`}>Something else? Paste the output of dmesg from that machine</label>
        <textarea
          id={`dmesg-${folder.name}`}
          value={dmesg}
          onChange={(e) => setDmesg(e.target.value)}
          rows={4}
          placeholder="dmesg | grep -iE 'firmware|failed to load'"
          disabled={running}
        />
        <button className="btn btn-secondary" onClick={scan} disabled={!dmesg.trim() || running}>
          Find missing firmware
        </button>
        <p className="tool-note">
          Or send it from the machine itself (in Kaspersky, in a terminal):
          <code className="krd-command">{command}</code>
        </p>
      </div>

      {info.reports.length > 0 && (
        <div className="krd-reports">
          <strong>Reports from machines</strong>
          <ul>
            {[...info.reports].reverse().map((r) => (
              <li key={`${r.at}-${r.client}`}>
                {r.at}, {r.client}: {r.missing.length ? r.missing.map((m) => m.name).join(', ') : 'nothing missing'}{' '}
                {r.missing.length > 0 && (
                  <button className="btn btn-secondary btn-small" onClick={() => applyMissing(r.missing)}>
                    Use
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {scanned && (
        <div className="krd-missing">
          <strong>Missing on that machine</strong>
          {missing.length === 0 && <p className="tool-note">No missing firmware found in that text.</p>}
          {missing.map((m) => (
            <label key={m.name} className="krd-check">
              <input
                type="checkbox"
                checked={!!picked[m.name]}
                onChange={(e) => setPicked((s) => ({ ...s, [m.name]: e.target.checked }))}
                disabled={running}
              />
              <span>
                <code>{m.name}</code>
                {m.alternatives.length > 0 && (
                  <small className="text-muted"> (older versions are tried if this one does not exist)</small>
                )}
              </span>
            </label>
          ))}
        </div>
      )}

      {running && (
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
        <button className="btn btn-primary" onClick={build} disabled={running || nothingChosen}>
          {running ? '⏳ Working…' : '🔧 Build small archive'}
        </button>
        <button className="btn btn-secondary" onClick={full} disabled={running}>
          Full set (436 MB)
        </button>
        {info.archives.length > 0 && (
          <button className="btn btn-secondary" onClick={remove} disabled={running}>
            Remove
          </button>
        )}
      </div>
      <p className="tool-note">
        Files come from the linux-firmware release {info.tag}, which matches the kernel of Kaspersky Rescue Disk 24.
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
        setSettings({ default: data.default, rules: data.rules })
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
                Apply the text size when the disk starts
                <small className="text-muted"> — the entries fetch a small script from this server</small>
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
