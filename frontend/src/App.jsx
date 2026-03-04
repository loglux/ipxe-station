import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'
import { CATEGORIES } from './data/scenarios'

// Placeholder components - we'll create these next
import MenuBuilder from './components/MenuBuilder/MenuBuilder'
import PropertyPanel from './components/PropertyPanel/PropertyPanel'
import AssetManager from './components/AssetManager/AssetManager'
import DHCPHelper from './components/DHCPHelper/DHCPHelper'
import AddEntryWizard from './components/Wizard/AddEntryWizard'
import Settings from './components/Settings/Settings'
import Monitoring from './components/Monitoring/Monitoring'
import BootFiles from './components/BootFiles/BootFiles'
import ConfirmDialog from './components/ConfirmDialog/ConfirmDialog'

function App() {
  const githubProfileUrl = import.meta.env.VITE_GITHUB_PROFILE_URL || 'https://github.com/loglux'
  const VALID_TABS = ['builder', 'assets', 'dhcp', 'boot', 'monitoring']
  const [activeTab, setActiveTab] = useState(() => {
    const saved = window.location.hash.slice(1)
    return VALID_TABS.includes(saved) ? saved : 'builder'
  })
  const switchTab = (tab) => {
    setActiveTab(tab)
    window.location.hash = tab
  }
  const [selectedEntryId, setSelectedEntryId] = useState(null)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsVersion, setSettingsVersion] = useState(0)
  const [wizardInitialCategory, setWizardInitialCategory] = useState(null)
  const [menuTitle, setMenuTitle] = useState('PXE Boot Menu')
  const [menuTimeout, setMenuTimeout] = useState(30000)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState(null)
  const [generatedScript, setGeneratedScript] = useState('')
  const [scriptWarnings, setScriptWarnings] = useState([])
  const [generatingScript, setGeneratingScript] = useState(false)
  const [entries, setEntries] = useState([])
  const generateAbortRef = useRef(null)

  const applyMenuFromResponse = (menu) => {
    setEntries(menu?.entries || [])
    setMenuTitle(menu?.title || 'PXE Boot Menu')
    setMenuTimeout(menu?.timeout || 30000)
  }

  const buildMenuPayload = useCallback(() => ({
    title: menuTitle,
    timeout: menuTimeout,
    entries,
  }), [entries, menuTimeout, menuTitle])

  // Auto-clear save messages after 5 s
  useEffect(() => {
    if (!saveMessage) return
    const timer = setTimeout(() => setSaveMessage(null), 5000)
    return () => clearTimeout(timer)
  }, [saveMessage])

  // Apply saved theme on mount
  useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(data => {
        document.documentElement.dataset.theme = data.theme === 'dark' ? 'dark' : ''
      })
      .catch(() => {})
  }, [])

  // Load saved menu structure on mount
  useEffect(() => {
    const loadMenu = async () => {
      try {
        const response = await fetch('/api/ipxe/menu/structure')
        const data = await response.json()

        if (data.success && data.menu) {
          applyMenuFromResponse(data.menu)
        } else {
          const fallback = await fetch('/api/ipxe/menu/default')
          const fallbackData = await fallback.json()
          if (fallbackData.success && fallbackData.menu) {
            applyMenuFromResponse(fallbackData.menu)
          }
        }
      } catch (error) {
        console.error('Failed to load menu:', error)
        try {
          const fallback = await fetch('/api/ipxe/menu/default')
          const fallbackData = await fallback.json()
          if (fallbackData.success && fallbackData.menu) {
            applyMenuFromResponse(fallbackData.menu)
          }
        } catch (fallbackError) {
          console.error('Failed to load default menu:', fallbackError)
        }
      }
    }

    loadMenu()
  }, [])

  const addEntry = (newEntry) => {
    setEntries(prev => [...prev, { ...newEntry, order: prev.length }])
  }

  const updateEntry = (entryName, updates) => {
    setEntries(prev => prev.map(e =>
      e.name === entryName ? { ...e, ...updates } : e
    ))
  }

  const deleteEntry = (entryName) => {
    setEntries(prev => prev.filter(e => e.name !== entryName))
    if (selectedEntryId === entryName) {
      setSelectedEntryId(null)
    }
  }

  const generateScript = useCallback(async () => {
    // Cancel any in-flight request before starting a new one
    if (generateAbortRef.current) {
      generateAbortRef.current.abort()
    }
    const controller = new AbortController()
    generateAbortRef.current = controller

    setGeneratingScript(true)

    try {
      const response = await fetch('/api/ipxe/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildMenuPayload()),
        signal: controller.signal,
      })

      const result = await response.json()

      if (result.valid) {
        setGeneratedScript(result.script || '')
        setScriptWarnings(result.warnings || [])
      } else {
        setGeneratedScript(`# Error generating script:\n# ${result.message}`)
        setScriptWarnings([])
      }
    } catch (error) {
      if (error.name === 'AbortError') return
      setGeneratedScript(`# Failed to generate: ${error.message}`)
      setScriptWarnings([])
    } finally {
      setGeneratingScript(false)
    }
  }, [buildMenuPayload])

  const saveMenu = async () => {
    setSaving(true)
    setSaveMessage(null)

    try {
      const response = await fetch('/api/ipxe/menu/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(buildMenuPayload()),
      })

      const result = await response.json()

      if (result.valid) {
        setSaveMessage({ type: 'success', text: '✅ Menu saved successfully!' })
        if (result.warnings && result.warnings.length > 0) {
          console.warn('Menu warnings:', result.warnings)
        }
      } else {
        setSaveMessage({ type: 'error', text: `❌ ${result.message}` })
      }
    } catch (error) {
      setSaveMessage({ type: 'error', text: `❌ Failed to save: ${error.message}` })
    } finally {
      setSaving(false)
    }
  }

  const deleteMenu = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/ipxe/menu', {
        method: 'DELETE',
      })

      const result = await response.json()

      if (result.success) {
        setSaveMessage({ type: 'success', text: `✅ ${result.message}` })
        const fallback = await fetch('/api/ipxe/menu/default')
        const fallbackData = await fallback.json()
        if (fallbackData.success && fallbackData.menu) {
          applyMenuFromResponse(fallbackData.menu)
        }
        setSelectedEntryId(null)
      } else {
        setSaveMessage({ type: 'error', text: `❌ ${result.message}` })
      }
    } catch (error) {
      setSaveMessage({ type: 'error', text: `❌ Failed to delete: ${error.message}` })
    } finally {
      setSaving(false)
    }
  }

  const selectedEntry = entries.find(e => e.name === selectedEntryId)

  const openWizard = (initialCategory = null) => {
    setWizardInitialCategory(initialCategory)
    setWizardOpen(true)
  }

  const closeWizard = () => {
    setWizardOpen(false)
    setWizardInitialCategory(null)
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <h1>🌐 iPXE Menu Builder</h1>
          <span className="version">v2.0 - Scenario-First Edition</span>
        </div>
        <div className="header-right">
          {saveMessage && (
            <div className={`save-message ${saveMessage.type}`}>
              {saveMessage.text}
            </div>
          )}
          <button className="btn btn-secondary" onClick={() => setSettingsOpen(true)}>⚙️ Settings</button>
          <button
            className="btn btn-danger"
            onClick={() => setDeleteConfirmOpen(true)}
            disabled={saving}
            title="Delete entire menu (boot.ipxe and menu.json)"
          >
            🗑️ Delete Menu
          </button>
          <button
            className="btn btn-primary"
            onClick={saveMenu}
            disabled={saving}
          >
            {saving ? '⏳ Saving...' : '💾 Save Menu'}
          </button>
        </div>
      </header>

      {/* Main Layout */}
      <div className={`main-layout${activeTab !== 'builder' ? ' full-width' : ''}`}>
        {/* Left Sidebar - Menu Tree (builder only) */}
        {activeTab === 'builder' && (
          <aside className="sidebar-left">
            <div className="sidebar-header">
              <h2>Menu Structure</h2>
            </div>
            <div className="sidebar-content">
              <MenuBuilder
                entries={entries}
                selectedEntryId={selectedEntryId}
                onSelectEntry={setSelectedEntryId}
                onOpenWizard={openWizard}
                onUpdateEntry={updateEntry}
                onDeleteEntry={deleteEntry}
              />
            </div>
          </aside>
        )}

        {/* Center - Main Content Area */}
        <main className="main-content">
          {/* Tabs */}
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'builder' ? 'active' : ''}`}
              onClick={() => { switchTab('builder'); setSelectedEntryId(null) }}
            >
              🏗️ Builder
            </button>
            <button
              className={`tab ${activeTab === 'assets' ? 'active' : ''}`}
              onClick={() => switchTab('assets')}
            >
              📦 Assets
            </button>
            <button
              className={`tab ${activeTab === 'dhcp' ? 'active' : ''}`}
              onClick={() => switchTab('dhcp')}
            >
              🌐 DHCP
            </button>
            <button
              className={`tab ${activeTab === 'boot' ? 'active' : ''}`}
              onClick={() => switchTab('boot')}
            >
              🚀 Boot Files
            </button>
            <button
              className={`tab ${activeTab === 'monitoring' ? 'active' : ''}`}
              onClick={() => switchTab('monitoring')}
            >
              📊 Monitoring
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'builder' && (
              <div className="builder-view">
                {selectedEntry ? (
                  <div className="builder-editor">
                    <PropertyPanel
                      entry={selectedEntry}
                      onUpdateEntry={updateEntry}
                      onDeleteEntry={deleteEntry}
                      entries={entries}
                    />
                  </div>
                ) : (
                  <div className="welcome-message">
                    <h2>Welcome to iPXE Menu Builder</h2>
                    <p>Select an entry from the menu structure or add a new one to get started.</p>

                    <div className="quick-actions">
                      <h3>Quick Actions</h3>
                      <div className="action-grid">
                        {Object.entries(CATEGORIES).map(([key, category]) => (
                          <div
                            key={key}
                            className="action-card"
                            style={{ borderColor: category.color }}
                            onClick={() => openWizard(key)}
                          >
                            <div className="action-icon">{category.icon}</div>
                            <div className="action-name">{category.name}</div>
                            <div className="action-description">{category.description}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Inline iPXE script preview */}
                <details
                  className="script-preview-drawer"
                  onToggle={(e) => { if (e.target.open) generateScript() }}
                >
                  <summary className="script-preview-toggle">
                    📜 iPXE Script Preview
                    {scriptWarnings.length > 0 && (
                      <span className="preview-warning-badge">{scriptWarnings.length} warning{scriptWarnings.length !== 1 ? 's' : ''}</span>
                    )}
                  </summary>
                  <div className="script-preview-body">
                    <div className="preview-actions">
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={generateScript}
                        disabled={generatingScript}
                      >
                        {generatingScript ? '⏳' : '🔄 Refresh'}
                      </button>
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={async () => {
                          const result = await fetch('/api/ipxe/generate', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(buildMenuPayload()),
                          }).then(r => r.json()).catch(() => null)
                          if (result?.script) {
                            try {
                              await navigator.clipboard.writeText(result.script)
                            } catch {
                              const ta = document.createElement('textarea')
                              ta.value = result.script
                              document.body.appendChild(ta)
                              ta.select()
                              document.execCommand('copy')
                              document.body.removeChild(ta)
                            }
                          }
                        }}
                      >
                        📋 Copy
                      </button>
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={async () => {
                          const result = await fetch('/api/ipxe/generate', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(buildMenuPayload()),
                          }).then(r => r.json()).catch(() => null)
                          if (result?.script) {
                            const blob = new Blob([result.script], { type: 'text/plain' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = 'boot.ipxe'
                            a.click()
                            URL.revokeObjectURL(url)
                          }
                        }}
                      >
                        💾 Download .ipxe
                      </button>
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => {
                          const blob = new Blob([JSON.stringify(buildMenuPayload(), null, 2)], { type: 'application/json' })
                          const url = URL.createObjectURL(blob)
                          const a = document.createElement('a')
                          a.href = url
                          a.download = 'menu.json'
                          a.click()
                          URL.revokeObjectURL(url)
                        }}
                      >
                        📄 Export JSON
                      </button>
                    </div>
                    {scriptWarnings.length > 0 && (
                      <div className="warnings-panel">
                        <h4>⚠️ Warnings</h4>
                        <ul>
                          {scriptWarnings.map((warning, i) => (
                            <li key={i}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <pre className="code-preview">
                      {generatingScript ? '# Generating script...' : (generatedScript || '# No script generated yet')}
                    </pre>
                  </div>
                </details>
              </div>
            )}

            {activeTab === 'assets' && <AssetManager />}
            {activeTab === 'dhcp' && <DHCPHelper settingsVersion={settingsVersion} />}
            {activeTab === 'boot' && <BootFiles />}
            {activeTab === 'monitoring' && <Monitoring />}
          </div>
        </main>

      </div>

      {/* Footer */}
      <footer className="app-footer">
        <div className="footer-left">
          <span>iPXE Station - Network Boot Made Easy</span>
          <span>•</span>
          <a
            className="footer-link"
            href={githubProfileUrl}
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </div>
        <div className="footer-right">
          <span>Entries: {entries.length}</span>
          <span>•</span>
          <span>Enabled: {entries.filter(e => e.enabled).length}</span>
        </div>
      </footer>

      {/* Global Add Entry Wizard */}
      <AddEntryWizard
        isOpen={wizardOpen}
        onClose={closeWizard}
        onAddEntry={(entry) => {
          addEntry(entry)
          closeWizard()
        }}
        entries={entries}
        initialCategory={wizardInitialCategory}
      />

      <Settings
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSave={() => setSettingsVersion(v => v + 1)}
      />

      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        title="Delete entire menu?"
        message="This will remove both boot.ipxe and menu.json. This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={() => { setDeleteConfirmOpen(false); deleteMenu() }}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </div>
  )
}

export default App
