import { useEffect, useMemo, useState } from 'react'
import './App.css'

const defaultMenu = {
  title: 'PXE Boot Menu',
  timeout: 30000,
  default_entry: 'ubuntu',
  server_ip: 'localhost',
  http_port: 8000,
  entries: [
    {
      name: 'ubuntu',
      title: 'Ubuntu Netboot',
      kernel: 'ubuntu/vmlinuz',
      initrd: 'ubuntu/initrd',
      cmdline: 'ip=dhcp',
      entry_type: 'boot',
      boot_mode: 'netboot',
    },
  ],
}

function App() {
  const [menuJson, setMenuJson] = useState(JSON.stringify(defaultMenu, null, 2))
  const [menuObj, setMenuObj] = useState(defaultMenu)
  const [script, setScript] = useState('')
  const [errors, setErrors] = useState([])
  const [warnings, setWarnings] = useState([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [lastSavePath, setLastSavePath] = useState('')
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState('')

  const syncJsonToObj = (text) => {
    try {
    const parsed = JSON.parse(text)
    setMenuObj(parsed)
    setErrors([])
  } catch (err) {
    setErrors([`JSON parse error: ${err.message}`])
    }
  }

  const updateField = (field, value) => {
    const next = { ...menuObj, [field]: value }
    setMenuObj(next)
    setMenuJson(JSON.stringify(next, null, 2))
  }

  const entries = useMemo(() => Array.isArray(menuObj.entries) ? menuObj.entries : [], [menuObj.entries])

  const reindexOrders = (list) => list.map((e, i) => ({ ...e, order: i + 1 }))

  const updateEntryField = (idx, field, value) => {
    let nextEntries = [...entries]

    if (field === 'order') {
      const target = Math.max(0, Math.min(Number(value) - 1, entries.length - 1))
      const [item] = nextEntries.splice(idx, 1)
      nextEntries.splice(target, 0, item)
    } else {
      nextEntries = nextEntries.map((e, i) => i === idx ? { ...e, [field]: value } : e)
    }

    const ordered = reindexOrders(nextEntries)
    const next = { ...menuObj, entries: ordered }
    setMenuObj(next)
    setMenuJson(JSON.stringify(next, null, 2))
  }

  const addEntry = () => {
    const nextEntries = [
      ...entries,
      {
        name: `entry_${entries.length + 1}`,
        title: `Entry ${entries.length + 1}`,
        entry_type: 'boot',
        boot_mode: 'netboot',
        kernel: '',
        initrd: '',
        cmdline: '',
        description: '',
        requires_iso: false,
        requires_internet: false,
        enabled: true,
        order: entries.length + 1,
      },
    ]
    const ordered = reindexOrders(nextEntries)
    const next = { ...menuObj, entries: ordered }
    setMenuObj(next)
    setMenuJson(JSON.stringify(next, null, 2))
  }

  const removeEntry = (idx) => {
    const nextEntries = reindexOrders(entries.filter((_, i) => i !== idx))
    const next = { ...menuObj, entries: nextEntries }
    setMenuObj(next)
    setMenuJson(JSON.stringify(next, null, 2))
  }

  const moveEntry = (idx, direction) => {
    const nextEntries = [...entries]
    if (direction === 'up' && idx > 0) {
      ;[nextEntries[idx - 1], nextEntries[idx]] = [nextEntries[idx], nextEntries[idx - 1]]
    }
    if (direction === 'down' && idx < nextEntries.length - 1) {
      ;[nextEntries[idx + 1], nextEntries[idx]] = [nextEntries[idx], nextEntries[idx + 1]]
    }
    const ordered = reindexOrders(nextEntries)
    const next = { ...menuObj, entries: ordered }
    setMenuObj(next)
    setMenuJson(JSON.stringify(next, null, 2))
  }

  const callApi = async (path) => {
    setLoading(true)
    setStatus('')
    setErrors([])
    setWarnings([])
    try {
      const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(menuObj),
      })
      const data = await resp.json()
      if (!resp.ok || data.valid === false) {
        setErrors(data.errors || [data.message || 'Validation failed'])
        setWarnings(data.warnings || [])
        setScript('')
        setStatus('❌ Validation failed')
        return
      }
      setWarnings(data.warnings || [])
      setScript(data.script || '')
      if (data.config_path) setLastSavePath(data.config_path)
      setStatus('✅ Success')
    } catch (err) {
      setErrors([String(err)])
      setStatus('❌ Request error')
    } finally {
      setLoading(false)
    }
  }

  const generate = () => callApi('/api/ipxe/generate')
  const validate = () => callApi('/api/ipxe/validate')

  const loadTemplate = async (name) => {
    setLoading(true)
    setStatus(`Loading template ${name}...`)
    try {
      const resp = await fetch(`/api/ipxe/templates/${name}`, { method: 'POST' })
      if (!resp.ok) throw new Error(`Template ${name} not found`)
      const data = await resp.json()
      setMenuObj(data)
      setMenuJson(JSON.stringify(data, null, 2))
      setStatus(`Loaded template ${name}`)
    } catch (err) {
      setErrors([String(err)])
      setStatus('❌ Template load failed')
    } finally {
      setLoading(false)
    }
  }

  const fetchTemplates = async () => {
    try {
      const resp = await fetch('/api/ipxe/templates')
      const data = await resp.json()
      setTemplates(data.templates || [])
    } catch (err) {
      // ignore for now
    }
  }

  useEffect(() => {
    fetchTemplates()
  }, [])

  const saveMenu = async () => {
    await callApi('/api/ipxe/menu/save')
  }

  return (
    <div className="app">
      <header>
        <h1>iPXE Menu Editor (API-driven)</h1>
        <p>Edit JSON or use the form, then validate/generate via backend. Warnings show lint output.</p>
      </header>

      <section className="controls">
        <div className="buttons">
          <button onClick={validate} disabled={loading}>Validate</button>
          <button onClick={generate} disabled={loading}>Generate</button>
          <button onClick={saveMenu} disabled={loading}>Save (boot.ipxe)</button>
          <select
            value={selectedTemplate}
            onChange={(e) => {
              const val = e.target.value
              setSelectedTemplate(val)
              if (val) loadTemplate(val)
            }}
            disabled={loading}
          >
            <option value="">Load template...</option>
            {templates.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="status">{loading ? '⏳ Working...' : status}</div>
      </section>

      <section className="editor-preview">
        <div className="form">
          <h3>Menu Fields</h3>
          <div className="form-grid">
            <label>
              Title
              <input value={menuObj.title || ''} onChange={(e) => updateField('title', e.target.value)} />
            </label>
            <label>
              Timeout (ms)
              <input type="number" value={menuObj.timeout || 0} onChange={(e) => updateField('timeout', Number(e.target.value))} />
            </label>
            <label>
              Default Entry
              <input value={menuObj.default_entry || ''} onChange={(e) => updateField('default_entry', e.target.value)} />
            </label>
            <label>
              Server IP
              <input value={menuObj.server_ip || ''} onChange={(e) => updateField('server_ip', e.target.value)} />
            </label>
            <label>
              HTTP Port
              <input type="number" value={menuObj.http_port || 0} onChange={(e) => updateField('http_port', Number(e.target.value))} />
            </label>
          </div>
        </div>
        <div className="editor">
          <h3>Menu JSON</h3>
          <textarea
            value={menuJson}
            onChange={(e) => {
              setMenuJson(e.target.value)
              syncJsonToObj(e.target.value)
            }}
            rows={24}
          />
        </div>
        <div className="preview">
          <h3>Warnings</h3>
          {warnings.length === 0 ? <div className="ok">None</div> : (
            <ul className="warnings">
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
          <h3>Errors</h3>
          {errors.length === 0 ? <div className="ok">None</div> : (
            <ul className="errors">
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
          <h3>Generated iPXE Script</h3>
          <div className="script-actions">
            <button onClick={() => navigator.clipboard.writeText(script || '')} disabled={!script}>Copy</button>
            {lastSavePath && <span className="save-path">Saved to: {lastSavePath}</span>}
          </div>
          <pre className="script">{script || '—'}</pre>
        </div>
        <div className="entries">
          <div className="entries-header">
            <h3>Entries ({entries.length})</h3>
            <button onClick={addEntry} disabled={loading}>Add Entry</button>
          </div>
          {entries.length === 0 ? <div className="ok">No entries</div> : (
            <div className="entries-table">
              <div className="entries-row entries-head">
                <div>#</div>
                <div>On</div>
                <div>Name</div>
                <div>Title</div>
                <div>Type</div>
                <div>Boot Mode</div>
                <div>Kernel</div>
                <div>Initrd</div>
                <div>Cmdline</div>
                <div>Description</div>
                <div>Requires</div>
                <div>Actions</div>
              </div>
              {entries.map((entry, idx) => (
                <div className="entries-row" key={idx}>
                  <div><input type="number" value={entry.order || idx + 1} onChange={(e) => updateEntryField(idx, 'order', Number(e.target.value))} /></div>
                  <div><input type="checkbox" checked={entry.enabled !== false} onChange={(e) => updateEntryField(idx, 'enabled', e.target.checked)} /></div>
                  <div><input value={entry.name || ''} onChange={(e) => updateEntryField(idx, 'name', e.target.value)} /></div>
                  <div><input value={entry.title || ''} onChange={(e) => updateEntryField(idx, 'title', e.target.value)} /></div>
                  <div>
                    <select value={entry.entry_type || 'boot'} onChange={(e) => updateEntryField(idx, 'entry_type', e.target.value)}>
                      <option value="boot">boot</option>
                      <option value="menu">menu</option>
                      <option value="action">action</option>
                      <option value="separator">separator</option>
                    </select>
                  </div>
                  <div>
                    <select value={entry.boot_mode || 'netboot'} onChange={(e) => updateEntryField(idx, 'boot_mode', e.target.value)}>
                      <option value="netboot">netboot</option>
                      <option value="live">live</option>
                      <option value="rescue">rescue</option>
                      <option value="preseed">preseed</option>
                      <option value="tool">tool</option>
                      <option value="custom">custom</option>
                    </select>
                  </div>
                  <div><input value={entry.kernel || ''} onChange={(e) => updateEntryField(idx, 'kernel', e.target.value)} /></div>
                  <div><input value={entry.initrd || ''} onChange={(e) => updateEntryField(idx, 'initrd', e.target.value)} /></div>
                  <div><input value={entry.cmdline || ''} onChange={(e) => updateEntryField(idx, 'cmdline', e.target.value)} /></div>
                  <div><input value={entry.description || ''} onChange={(e) => updateEntryField(idx, 'description', e.target.value)} /></div>
                  <div className="requires">
                    <label><input type="checkbox" checked={!!entry.requires_iso} onChange={(e) => updateEntryField(idx, 'requires_iso', e.target.checked)} /> ISO</label>
                    <label><input type="checkbox" checked={!!entry.requires_internet} onChange={(e) => updateEntryField(idx, 'requires_internet', e.target.checked)} /> Internet</label>
                  </div>
                  <div className="entry-actions">
                    <button onClick={() => moveEntry(idx, 'up')} disabled={idx === 0 || loading}>↑</button>
                    <button onClick={() => moveEntry(idx, 'down')} disabled={idx === entries.length - 1 || loading}>↓</button>
                    <button onClick={() => removeEntry(idx)} disabled={loading}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default App
