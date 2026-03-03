import { useState, useEffect, useCallback } from 'react'
import './BootFiles.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

function BootFiles() {
  const [autoexec, setAutoexec] = useState('')
  const [preseed, setPreseed] = useState('')
  const [preseedProfiles, setPreseedProfiles] = useState([])
  const [selectedPreseedProfile, setSelectedPreseedProfile] = useState('debian_minimal')
  const [activePreseedProfile, setActivePreseedProfile] = useState('debian_minimal')
  const [newPreseedProfile, setNewPreseedProfile] = useState('')
  const [disableConfirmOpen, setDisableConfirmOpen] = useState(false)
  const [deletePreseedConfirmOpen, setDeletePreseedConfirmOpen] = useState(false)
  const [templates, setTemplates] = useState({})
  const [preseedTemplates, setPreseedTemplates] = useState({})
  const [selectedTemplate, setSelectedTemplate] = useState('direct')
  const [selectedPreseedTemplate, setSelectedPreseedTemplate] = useState('debian_minimal')
  const [fileExists, setFileExists] = useState(true)
  const [preseedExists, setPreseedExists] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [settings, setSettings] = useState({ server_ip: '', http_port: 9021 })

  const loadPreseedProfile = useCallback(async (profileName = null) => {
    const profile = profileName || selectedPreseedProfile
    const response = await fetch(`/api/boot/preseed?profile=${encodeURIComponent(profile)}`)
    const data = await response.json()
    setPreseedExists(data.exists)
    setPreseed(data.exists ? data.content : '')
    if (data.profile) setSelectedPreseedProfile(data.profile)
    if (data.active_profile) setActivePreseedProfile(data.active_profile)
  }, [selectedPreseedProfile])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const settingsRes = await fetch('/api/settings')
      const settingsData = await settingsRes.json()
      setSettings(settingsData)

      const templatesRes = await fetch('/api/boot/autoexec/templates')
      const templatesData = await templatesRes.json()
      setTemplates(templatesData.templates)

      const preseedTemplatesRes = await fetch('/api/boot/preseed/templates')
      const preseedTemplatesData = await preseedTemplatesRes.json()
      setPreseedTemplates(preseedTemplatesData.templates)

      const profilesRes = await fetch('/api/boot/preseed/profiles')
      const profilesData = await profilesRes.json()
      const profiles = profilesData.profiles || []
      const active = profilesData.active_profile || settingsData.active_preseed_profile || 'debian_minimal'
      setPreseedProfiles(profiles)
      setActivePreseedProfile(active)
      const selected = profiles.includes(selectedPreseedProfile) ? selectedPreseedProfile : active
      setSelectedPreseedProfile(selected)

      const autoexecRes = await fetch('/api/boot/autoexec')
      const autoexecData = await autoexecRes.json()
      setFileExists(autoexecData.exists)
      if (autoexecData.exists) {
        setAutoexec(autoexecData.content)
      } else {
        setAutoexec('')
      }

      await loadPreseedProfile(selected)
    } catch (error) {
      showMessage('error', `Failed to load data: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }, [loadPreseedProfile, selectedPreseedProfile])

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

  const applyPreseedTemplate = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/boot/preseed/apply-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template: selectedPreseedTemplate,
          profile: newPreseedProfile || selectedPreseedProfile,
          activate: true
        })
      })

      const result = await response.json()

      if (result.success) {
        setPreseed(result.content)
        setPreseedExists(true)
        setSelectedPreseedProfile(result.profile)
        setActivePreseedProfile(result.active_profile)
        setNewPreseedProfile('')
        await loadData()
        showMessage('success', `✅ ${result.message}`)
      } else {
        showMessage('error', '❌ Failed to apply preseed template')
      }
    } catch (error) {
      showMessage('error', `❌ Error: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const savePreseed = async () => {
    setSaving(true)
    try {
      const profile = newPreseedProfile || selectedPreseedProfile
      const response = await fetch('/api/boot/preseed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile,
          content: preseed,
          activate: true
        })
      })

      const result = await response.json()

      if (result.success) {
        setPreseedExists(true)
        setSelectedPreseedProfile(result.profile)
        setActivePreseedProfile(result.active_profile)
        setNewPreseedProfile('')
        await loadData()
        showMessage('success', `✅ Saved preseed profile '${result.profile}' (${result.size} bytes)`)
      } else {
        showMessage('error', '❌ Failed to save preseed.cfg')
      }
    } catch (error) {
      showMessage('error', `❌ Error: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const deletePreseed = async () => {
    setSaving(true)
    try {
      const response = await fetch(`/api/boot/preseed?profile=${encodeURIComponent(selectedPreseedProfile)}`, {
        method: 'DELETE'
      })

      const result = await response.json()

      if (result.success) {
        setPreseed('')
        setPreseedExists(false)
        setActivePreseedProfile(result.active_profile || 'debian_minimal')
        await loadData()
        showMessage('success', `✅ ${result.message}`)
      } else {
        showMessage('error', '❌ Failed to delete preseed.cfg')
      }
    } catch (error) {
      showMessage('error', `❌ Error: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const activatePreseed = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/boot/preseed/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: selectedPreseedProfile })
      })
      const result = await response.json()
      if (result.success) {
        setActivePreseedProfile(result.active_profile)
        await loadData()
        showMessage('success', `✅ Activated preseed profile '${result.active_profile}'`)
      } else {
        showMessage('error', '❌ Failed to activate preseed profile')
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

      <div className="section" style={{ marginTop: '20px' }}>
        <h2>preseed.cfg</h2>
        <p className="section-description">
          Debian automated installer profiles served by the backend. The active profile is exposed at
          {' '}<code>http://{settings.server_ip || 'SERVER'}:{settings.http_port}/preseed.cfg</code>,
          and named profiles are also available at
          {' '}<code>http://{settings.server_ip || 'SERVER'}:{settings.http_port}/preseed/PROFILE.cfg</code>.
        </p>

        {!preseedExists && (
          <div className="message warning" style={{ marginBottom: '16px' }}>
            ⚠️ <strong>preseed profile not found</strong> — Debian Preseed entries will boot, but unattended install
            settings will be missing until you create or activate a profile.
          </div>
        )}

        <div className="template-selector">
          <label>Profiles:</label>
          <div className="template-buttons" style={{ marginBottom: '8px' }}>
            {preseedProfiles.map((profile) => (
              <button
                key={profile}
                className={`template-btn ${selectedPreseedProfile === profile ? 'active' : ''}`}
                onClick={async () => {
                  setSelectedPreseedProfile(profile)
                  await loadPreseedProfile(profile)
                }}
                title={profile === activePreseedProfile ? 'Active profile' : 'Preseed profile'}
              >
                {profile}{profile === activePreseedProfile ? ' ★' : ''}
              </button>
            ))}
          </div>
          <input
            className="form-control"
            style={{ marginBottom: '12px' }}
            type="text"
            value={newPreseedProfile}
            onChange={(e) => setNewPreseedProfile(e.target.value.replace(/[^a-zA-Z0-9_-]/g, ''))}
            placeholder="new profile name (optional)"
          />
          <label>Templates:</label>
          <div className="template-buttons">
            {Object.entries(preseedTemplates).map(([key, template]) => (
              <button
                key={key}
                className={`template-btn ${selectedPreseedTemplate === key ? 'active' : ''}`}
                onClick={() => setSelectedPreseedTemplate(key)}
                title={template.description}
              >
                {template.name}
              </button>
            ))}
          </div>
          <button
            className="btn btn-secondary"
            onClick={applyPreseedTemplate}
            disabled={saving}
          >
            Apply
          </button>
        </div>

        {preseedTemplates[selectedPreseedTemplate] && (
          <div className="template-info">
            <strong>{preseedTemplates[selectedPreseedTemplate].name}</strong>
            <p>{preseedTemplates[selectedPreseedTemplate].description}</p>
            <p>
              Active profile: <code>{activePreseedProfile}</code>
              {selectedPreseedProfile !== activePreseedProfile && (
                <> · Editing: <code>{selectedPreseedProfile}</code></>
              )}
            </p>
          </div>
        )}

        <div className="code-editor">
          <textarea
            value={preseed}
            onChange={(e) => setPreseed(e.target.value)}
            spellCheck={false}
            placeholder="# Debian preseed template"
          />
        </div>

        <div className="editor-actions">
          <button
            className="btn btn-primary"
            onClick={savePreseed}
            disabled={saving}
          >
            💾 Save
          </button>
          <button
            className="btn btn-secondary"
            onClick={activatePreseed}
            disabled={saving || selectedPreseedProfile === activePreseedProfile}
          >
            ⭐ Activate
          </button>
          <button
            className="btn btn-secondary"
            onClick={loadData}
          >
            🔄 Reload
          </button>
          <button
            className="btn btn-danger"
            onClick={() => setDeletePreseedConfirmOpen(true)}
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
      <ConfirmDialog
        isOpen={deletePreseedConfirmOpen}
        title={`Delete preseed profile '${selectedPreseedProfile}'?`}
        message="If this is the active profile, /preseed.cfg will switch to another saved profile."
        confirmLabel="Delete"
        danger
        onConfirm={() => { setDeletePreseedConfirmOpen(false); deletePreseed() }}
        onCancel={() => setDeletePreseedConfirmOpen(false)}
      />
    </div>
  )
}

export default BootFiles
