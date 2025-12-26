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

  const updateEntryField = (idx, field, value) => {
    const nextEntries = entries.map((e, i) => i === idx ? { ...e, [field]: value } : e)
    const next = { ...menuObj, entries: nextEntries }
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
      },
    ]
    const next = { ...menuObj, entries: nextEntries }
    setMenuObj(next)
    setMenuJson(JSON.stringify(next, null, 2))
  }

  const removeEntry = (idx) => {
    const nextEntries = entries.filter((_, i) => i !== idx)
    const next = { ...menuObj, entries: nextEntries }
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
          <button onClick={() => loadTemplate('ubuntu_multi')} disabled={loading}>Load Ubuntu Multi Template</button>
          <button onClick={() => loadTemplate('diagnostic')} disabled={loading}>Load Diagnostic Template</button>
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
                <div>Name</div>
                <div>Title</div>
                <div>Type</div>
                <div>Boot Mode</div>
                <div>Kernel</div>
                <div>Initrd</div>
                <div>Actions</div>
              </div>
              {entries.map((entry, idx) => (
                <div className="entries-row" key={idx}>
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
                  <div>
                    <button onClick={() => removeEntry(idx)} disabled={loading}>Remove</button>
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
