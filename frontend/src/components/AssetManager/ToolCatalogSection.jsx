import { useState, useEffect, useCallback, useRef } from 'react'
import DownloadProgressBlock from './DownloadProgressBlock'
import './ToolCatalogSection.css'

const POLL_MS = 1500

function checksumNote(version) {
  if (!version?.checksum) return 'No published checksum: the file is downloaded without verification.'
  const algo = version.checksum.split(':')[0]
  return algo === 'sha256'
    ? 'Verified with SHA-256 after download; a file that does not match is discarded.'
    : 'Verified with SHA-1 after download (the publisher offers nothing stronger); a file that does not match is discarded.'
}

/**
 * Tools that can be downloaded from their official releases (versions and checksums come from the
 * server). Downloading extracts the ISO like the other tools; use Add Entry to put it in the menu.
 */
export default function ToolCatalogSection({ catalog = {}, onDownloaded }) {
  const [tools, setTools] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState({})
  const [busy, setBusy] = useState({})
  const [progress, setProgress] = useState({})
  const [messages, setMessages] = useState({})
  const timers = useRef({})

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const response = await fetch('/api/assets/tools')
        if (!response.ok) throw new Error(`Server answered ${response.status}`)
        const data = await response.json()
        if (cancelled) return
        setTools(data.tools || [])
        setSelected(
          Object.fromEntries(
            (data.tools || []).map((t) => [t.id, (t.versions.find((v) => v.recommended) || t.versions[0])?.version]),
          ),
        )
      } catch (err) {
        if (!cancelled) setError(err.message || 'Could not load the tool list')
      } finally {
        if (!cancelled) setLoaded(true)
      }
    })()
    const running = timers.current
    return () => {
      cancelled = true
      Object.values(running).forEach(clearInterval)
    }
  }, [])

  const pickedVersion = (tool) => tool.versions.find((v) => v.version === selected[tool.id]) || tool.versions[0]

  const isInstalled = (tool, version) =>
    (catalog[tool.catalog_key] || []).some((row) => String(row.version) === String(version?.version))

  const download = useCallback(
    async (tool) => {
      const version = tool.versions.find((v) => v.version === selected[tool.id]) || tool.versions[0]
      if (!version) return
      const key = `${version.dest_folder}/${version.iso_name}`
      setBusy((b) => ({ ...b, [tool.id]: true }))
      setMessages((m) => ({ ...m, [tool.id]: null }))
      timers.current[tool.id] = setInterval(async () => {
        try {
          const response = await fetch('/api/assets/download/progress')
          const data = await response.json()
          setProgress(data.downloads || {})
        } catch {
          /* the next tick tries again */
        }
      }, POLL_MS)
      try {
        const response = await fetch('/api/assets/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: version.iso_url, dest: key, checksum: version.checksum || '' }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data.detail || `Server answered ${response.status}`)
        setMessages((m) => ({
          ...m,
          [tool.id]: { ok: true, text: version.checksum ? 'Downloaded and verified.' : 'Downloaded.' },
        }))
        if (onDownloaded) onDownloaded()
      } catch (err) {
        setMessages((m) => ({ ...m, [tool.id]: { ok: false, text: err.message } }))
      } finally {
        clearInterval(timers.current[tool.id])
        delete timers.current[tool.id]
        setBusy((b) => ({ ...b, [tool.id]: false }))
      }
    },
    [selected, onDownloaded],
  )

  return (
    <section className="asset-section tool-catalog">
      <h3>🧰 More tools</h3>
      <p className="text-sm text-muted download-section-note">
        Download from the official releases. After the download, use <strong>Add Entry</strong> in the Builder to
        put the tool in the boot menu.
      </p>

      {error && (
        <div className="tool-error" role="alert">
          Could not load the tool list: {error}
        </div>
      )}
      {!loaded && <small className="text-muted">Loading…</small>}

      {tools.map((tool) => {
        const version = pickedVersion(tool)
        const key = version ? `${version.dest_folder}/${version.iso_name}` : ''
        const message = messages[tool.id]
        const installed = isInstalled(tool, version)
        return (
          <div key={tool.id} className="download-subsection tool-card">
            <h4>
              {tool.icon} {tool.name}
              {installed && <span className="file-badge">✓ on disk</span>}
            </h4>
            <p className="text-sm text-muted download-section-note">
              {tool.description}{' '}
              <a href={tool.homepage} target="_blank" rel="noopener noreferrer">
                Website
              </a>
            </p>
            {tool.warning && (
              <div className="tool-warning" role="note">
                ⚠️ {tool.warning}
              </div>
            )}
            {version && (
              <div className="download-picker">
                <label htmlFor={`tool-${tool.id}`}>Version</label>
                <select
                  id={`tool-${tool.id}`}
                  value={version.version}
                  onChange={(e) => setSelected((s) => ({ ...s, [tool.id]: e.target.value }))}
                  disabled={busy[tool.id]}
                >
                  {tool.versions.map((v) => (
                    <option key={v.version} value={v.version}>
                      {v.name} ({v.size_est})
                    </option>
                  ))}
                </select>
                {version.notes && <p className="tool-note">{version.notes}</p>}
                <p className="tool-note">{checksumNote(version)}</p>
                {(busy[tool.id] || progress[key]) && progress[key] && (
                  <DownloadProgressBlock
                    title={`${tool.name} ISO`}
                    progress={progress[key]}
                    tone="success"
                    unit="GB"
                    divisor={1024 * 1024 * 1024}
                    decimals={2}
                    showExtraction
                  />
                )}
                {message && (
                  <div className={message.ok ? 'download-status' : 'tool-error'} role={message.ok ? 'status' : 'alert'}>
                    {message.text}
                  </div>
                )}
                <div className="download-picker-actions">
                  <button className="btn btn-primary" onClick={() => download(tool)} disabled={busy[tool.id]}>
                    {busy[tool.id] ? '⏳ Downloading...' : installed ? '⬇️ Download again' : '⬇️ Download ISO'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}
