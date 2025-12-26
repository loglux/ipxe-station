import { useEffect, useState } from 'react'
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
  const [script, setScript] = useState('')
  const [errors, setErrors] = useState([])
  const [warnings, setWarnings] = useState([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')

  const callApi = async (path) => {
    setLoading(true)
    setStatus('')
    setErrors([])
    setWarnings([])
    try {
      const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: menuJson,
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
      setMenuJson(JSON.stringify(data, null, 2))
      setStatus(`Loaded template ${name}`)
    } catch (err) {
      setErrors([String(err)])
      setStatus('❌ Template load failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // no-op
  }, [])

  return (
    <div className="app">
      <header>
        <h1>iPXE Menu Editor (API-driven)</h1>
        <p>Edit JSON, validate/generate via backend. Warnings show lint output.</p>
      </header>

      <section className="controls">
        <div className="buttons">
          <button onClick={validate} disabled={loading}>Validate</button>
          <button onClick={generate} disabled={loading}>Generate</button>
          <button onClick={() => loadTemplate('ubuntu_multi')} disabled={loading}>Load Ubuntu Multi Template</button>
          <button onClick={() => loadTemplate('diagnostic')} disabled={loading}>Load Diagnostic Template</button>
        </div>
        <div className="status">{loading ? '⏳ Working...' : status}</div>
      </section>

      <section className="editor-preview">
        <div className="editor">
          <h3>Menu JSON</h3>
          <textarea
            value={menuJson}
            onChange={(e) => setMenuJson(e.target.value)}
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
