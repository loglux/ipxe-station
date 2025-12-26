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
      </section>
    </div>
  )
}

export default App
