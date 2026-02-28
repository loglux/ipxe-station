import { useState, useEffect, useCallback } from 'react'
import './BootFiles.css'

function BootFiles() {
  const [autoexec, setAutoexec] = useState('')
  const [templates, setTemplates] = useState({})
  const [selectedTemplate, setSelectedTemplate] = useState('direct')
  const [bootFiles, setBootFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [settings, setSettings] = useState({ server_ip: '192.168.10.32', http_port: 9021 })

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      // Load settings
      const settingsRes = await fetch('/api/settings')
      const settingsData = await settingsRes.json()
      setSettings(settingsData)

      // Load templates
      const templatesRes = await fetch('/api/boot/autoexec/templates')
      const templatesData = await templatesRes.json()
      setTemplates(templatesData.templates)

      // Load current autoexec
      const autoexecRes = await fetch('/api/boot/autoexec')
      const autoexecData = await autoexecRes.json()
      if (autoexecData.exists) {
        setAutoexec(autoexecData.content)
      }

      // Load boot files
      const filesRes = await fetch('/api/boot/files')
      const filesData = await filesRes.json()
      setBootFiles(filesData.files)
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
    if (!confirm('Disable autoexec.ipxe bootstrap script? iPXE clients will need to boot directly to boot.ipxe via DHCP/chainloading.')) {
      return
    }

    setSaving(true)
    try {
      const response = await fetch('/api/boot/autoexec', {
        method: 'DELETE'
      })

      const result = await response.json()

      if (result.success) {
        setAutoexec('')
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

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  if (loading) {
    return <div className="boot-files-loading">Loading boot files...</div>
  }

  return (
    <div className="boot-files">
      {message && (
        <div className={`message ${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="boot-files-layout">
        {/* Left: Templates & Editor */}
        <div className="boot-files-editor">
          <div className="section">
            <h2>autoexec.ipxe Editor</h2>
            <p className="section-description">
              Optional bootstrap script for advanced or legacy flows. Recommended setups can boot iPXE clients directly to boot.ipxe without this file.
            </p>

            {/* Template Selector */}
            <div className="template-selector">
              <label>Quick Templates:</label>
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
                Apply Template
              </button>
            </div>

            {/* Template Description */}
            {templates[selectedTemplate] && (
              <div className="template-info">
                <strong>{templates[selectedTemplate].name}</strong>
                <p>{templates[selectedTemplate].description}</p>
              </div>
            )}

            {/* Code Editor */}
            <div className="code-editor">
              <textarea
                value={autoexec}
                onChange={(e) => setAutoexec(e.target.value)}
                spellCheck={false}
                placeholder="# iPXE script will appear here"
              />
            </div>

            <div className="editor-actions">
              <button
                className="btn btn-primary"
                onClick={saveAutoexec}
                disabled={saving}
              >
                💾 Save autoexec.ipxe
              </button>
              <button
                className="btn btn-secondary"
                onClick={loadData}
              >
                🔄 Reload
              </button>
              <button
                className="btn btn-danger"
                onClick={disableAutoexec}
                disabled={saving}
              >
                📴 Disable autoexec.ipxe
              </button>
            </div>
          </div>
        </div>

        {/* Right: Boot Files List */}
        <div className="boot-files-list">
          <div className="section">
            <h2>Boot Files</h2>
            <p className="section-description">
              Files in TFTP root directory. These are served via TFTP for network boot.
            </p>

            <div className="files-table">
              <table>
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Size</th>
                    <th>Modified</th>
                  </tr>
                </thead>
                <tbody>
                  {bootFiles.map((file) => (
                    <tr key={file.name}>
                      <td>
                        <span className={`file-icon ${file.executable ? 'executable' : ''}`}>
                          {file.name.endsWith('.ipxe') ? '📜' :
                           file.name.endsWith('.efi') ? '💾' :
                           file.name.endsWith('.kpxe') ? '💾' : '📄'}
                        </span>
                        {file.name}
                      </td>
                      <td>{formatFileSize(file.size)}</td>
                      <td className="file-date">{formatDate(file.modified)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default BootFiles
