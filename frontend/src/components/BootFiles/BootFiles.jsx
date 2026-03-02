import { useState, useEffect, useCallback } from 'react'
import './BootFiles.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

function BootFiles() {
  const [autoexec, setAutoexec] = useState('')
  const [disableConfirmOpen, setDisableConfirmOpen] = useState(false)
  const [templates, setTemplates] = useState({})
  const [selectedTemplate, setSelectedTemplate] = useState('direct')
  const [fileExists, setFileExists] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [settings, setSettings] = useState({ server_ip: '', http_port: 9021 })

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const settingsRes = await fetch('/api/settings')
      const settingsData = await settingsRes.json()
      setSettings(settingsData)

      const templatesRes = await fetch('/api/boot/autoexec/templates')
      const templatesData = await templatesRes.json()
      setTemplates(templatesData.templates)

      const autoexecRes = await fetch('/api/boot/autoexec')
      const autoexecData = await autoexecRes.json()
      setFileExists(autoexecData.exists)
      if (autoexecData.exists) {
        setAutoexec(autoexecData.content)
      } else {
        setAutoexec('')
      }
    } catch (error) {
      showMessage('error', `Failed to load data: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const showMessage = (type, text) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 5000)
  }

  const applyTemplate = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/boot/autoexec/apply-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template: selectedTemplate,
          next_server: settings.server_ip,
          http_port: settings.http_port
        })
      })

      const result = await response.json()

      if (result.success) {
        setAutoexec(result.content)
        setFileExists(true)
        showMessage('success', `✅ ${result.message}`)
      } else {
        showMessage('error', `❌ Failed to apply template`)
      }
    } catch (error) {
      showMessage('error', `❌ Error: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const saveAutoexec = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/boot/autoexec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: autoexec })
      })

      const result = await response.json()

      if (result.success) {
        setFileExists(true)
        showMessage('success', `✅ Saved (${result.size} bytes)`)
      } else {
        showMessage('error', `❌ Failed to save`)
      }
    } catch (error) {
      showMessage('error', `❌ Error: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const disableAutoexec = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/boot/autoexec', {
        method: 'DELETE'
      })

      const result = await response.json()

      if (result.success) {
        setAutoexec('')
        setFileExists(false)
        showMessage('success', `✅ ${result.message}`)
      } else {
        showMessage('error', '❌ Failed to disable autoexec.ipxe')
      }
    } catch (error) {
      showMessage('error', `❌ Error: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="boot-files-loading">Loading...</div>
  }

  return (
    <div className="boot-files">
      {message && (
        <div className={`message ${message.type}`}>
          {message.text}
        </div>
      )}

      {!fileExists && (
        <div className="message warning" style={{ marginBottom: '16px' }}>
          ⚠️ <strong>autoexec.ipxe not found</strong> — iPXE clients won't chain to boot.ipxe.
          Select a template below and click <strong>Apply</strong> to create it.
        </div>
      )}

      <div className="section">
        <h2>autoexec.ipxe</h2>
        <p className="section-description">
          TFTP bootstrap script — the first iPXE script a client fetches after loading the iPXE binary.
          Its job is to chain to <code>boot.ipxe</code> over HTTP. Use a template below, or write your own.
        </p>

        <div className="template-selector">
          <label>Templates:</label>
          <div className="template-buttons">
            {Object.entries(templates).map(([key, template]) => (
              <button
                key={key}
                className={`template-btn ${selectedTemplate === key ? 'active' : ''}`}
                onClick={() => setSelectedTemplate(key)}
                title={template.description}
              >
                {template.name}
              </button>
            ))}
          </div>
          <button
            className="btn btn-secondary"
            onClick={applyTemplate}
            disabled={saving}
          >
            Apply
          </button>
        </div>

        {templates[selectedTemplate] && (
          <div className="template-info">
            <strong>{templates[selectedTemplate].name}</strong>
            <p>{templates[selectedTemplate].description}</p>
          </div>
        )}

        <div className="code-editor">
          <textarea
            value={autoexec}
            onChange={(e) => setAutoexec(e.target.value)}
            spellCheck={false}
            placeholder="#!ipxe&#10;chain http://SERVER_IP:PORT/ipxe/boot.ipxe"
          />
        </div>

        <div className="editor-actions">
          <button
            className="btn btn-primary"
            onClick={saveAutoexec}
            disabled={saving}
          >
            💾 Save
          </button>
          <button
            className="btn btn-secondary"
            onClick={loadData}
          >
            🔄 Reload
          </button>
          <button
            className="btn btn-danger"
            onClick={() => setDisableConfirmOpen(true)}
            disabled={saving}
          >
            🗑️ Delete
          </button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={disableConfirmOpen}
        title="Delete autoexec.ipxe?"
        message="iPXE clients will need to boot directly to boot.ipxe via DHCP/chainloading."
        confirmLabel="Delete"
        danger
        onConfirm={() => { setDisableConfirmOpen(false); disableAutoexec() }}
        onCancel={() => setDisableConfirmOpen(false)}
      />
    </div>
  )
}

export default BootFiles
