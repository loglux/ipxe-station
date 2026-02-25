import { useState, useEffect } from 'react'
import './Settings.css'

export default function Settings({ isOpen, onClose }) {
  const [settings, setSettings] = useState({
    server_ip: '192.168.10.32',
    http_port: 9021,
    tftp_port: 69,
    default_timeout: 30000,
    default_entry: '',
    auto_extraction: true,
    poll_interval: 2000,
    theme: 'light',
    show_file_sizes: true,
    show_timestamps: true
  })

  const [detecting, setDetecting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
      fetchSettings()
    }
  }, [isOpen])

  const fetchSettings = async () => {
    try {
      const response = await fetch('/api/settings')
      const data = await response.json()
      setSettings(data)
    } catch (error) {
      console.error('Failed to load settings:', error)
    }
  }

  const detectIP = async () => {
    setDetecting(true)
    try {
      const response = await fetch('/api/network/detect')
      const data = await response.json()

      if (data.detected_ip) {
        setSettings(prev => ({ ...prev, server_ip: data.detected_ip }))
        setMessage({ type: 'success', text: `Detected IP: ${data.detected_ip}` })
        setTimeout(() => setMessage(null), 3000)
      }
    } catch {
      setMessage({ type: 'error', text: 'Failed to detect IP address' })
      setTimeout(() => setMessage(null), 3000)
    } finally {
      setDetecting(false)
    }
  }

  const saveSettings = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      })

      const data = await response.json()
      if (data.success) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' })
        setTimeout(() => {
          setMessage(null)
          onClose()
        }, 1500)
      }
    } catch {
      setMessage({ type: 'error', text: 'Failed to save settings' })
      setTimeout(() => setMessage(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  const handleChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }))
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content settings-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>⚙️ Settings</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {message && (
            <div className={`message ${message.type}`}>
              {message.text}
            </div>
          )}

          {/* Network Settings */}
          <section className="settings-section">
            <h3>🌐 Network Settings</h3>
            <div className="setting-group">
              <label>
                Server IP Address:
                <div className="input-with-button">
                  <input
                    type="text"
                    value={settings.server_ip}
                    onChange={e => handleChange('server_ip', e.target.value)}
                    placeholder="192.168.10.32"
                  />
                  <button
                    className="btn btn-secondary"
                    onClick={detectIP}
                    disabled={detecting}
                  >
                    {detecting ? '🔍 Detecting...' : '🔍 Auto-detect'}
                  </button>
                </div>
              </label>
            </div>
            <div className="setting-row">
              <label>
                HTTP Port:
                <input
                  type="number"
                  value={settings.http_port}
                  onChange={e => handleChange('http_port', parseInt(e.target.value))}
                  min="1"
                  max="65535"
                />
              </label>
              <label>
                TFTP Port:
                <input
                  type="number"
                  value={settings.tftp_port}
                  onChange={e => handleChange('tftp_port', parseInt(e.target.value))}
                  min="1"
                  max="65535"
                />
              </label>
            </div>
          </section>

          {/* Boot Settings */}
          <section className="settings-section">
            <h3>🚀 Boot Settings</h3>
            <div className="setting-group">
              <label>
                Default Timeout (milliseconds):
                <input
                  type="number"
                  value={settings.default_timeout}
                  onChange={e => handleChange('default_timeout', parseInt(e.target.value))}
                  min="0"
                  step="1000"
                />
                <small>{(settings.default_timeout / 1000).toFixed(0)} seconds</small>
              </label>
            </div>
            <div className="setting-group">
              <label>
                Default Menu Entry:
                <input
                  type="text"
                  value={settings.default_entry}
                  onChange={e => handleChange('default_entry', e.target.value)}
                  placeholder="Leave empty for no default"
                />
              </label>
            </div>
          </section>

          {/* Functions */}
          <section className="settings-section">
            <h3>⚡ Functions</h3>
            <div className="setting-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.auto_extraction}
                  onChange={e => handleChange('auto_extraction', e.target.checked)}
                />
                <span>Auto-extract ISO files after download</span>
              </label>
            </div>
            <div className="setting-group">
              <label>
                Download Progress Poll Interval (milliseconds):
                <input
                  type="number"
                  value={settings.poll_interval}
                  onChange={e => handleChange('poll_interval', parseInt(e.target.value))}
                  min="1000"
                  max="10000"
                  step="500"
                />
                <small>{(settings.poll_interval / 1000).toFixed(1)} seconds</small>
              </label>
            </div>
          </section>

          {/* Display Settings */}
          <section className="settings-section">
            <h3>🎨 Display</h3>
            <div className="setting-group">
              <label>
                Theme:
                <select
                  value={settings.theme}
                  onChange={e => handleChange('theme', e.target.value)}
                >
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </select>
              </label>
            </div>
            <div className="setting-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.show_file_sizes}
                  onChange={e => handleChange('show_file_sizes', e.target.checked)}
                />
                <span>Show file sizes in asset list</span>
              </label>
            </div>
            <div className="setting-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.show_timestamps}
                  onChange={e => handleChange('show_timestamps', e.target.checked)}
                />
                <span>Show timestamps in asset list</span>
              </label>
            </div>
          </section>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={saveSettings}
            disabled={saving}
          >
            {saving ? '💾 Saving...' : '💾 Save Settings'}
          </button>
        </div>
      </div>
    </div>
  )
}
