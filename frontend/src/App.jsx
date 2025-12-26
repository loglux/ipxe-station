import { useState, useEffect } from 'react'
import './App.css'
import { CATEGORIES } from './data/scenarios'

// Placeholder components - we'll create these next
import MenuBuilder from './components/MenuBuilder/MenuBuilder'
import PropertyPanel from './components/PropertyPanel/PropertyPanel'
import AssetManager from './components/AssetManager/AssetManager'
import DHCPHelper from './components/DHCPHelper/DHCPHelper'

function App() {
  const [activeTab, setActiveTab] = useState('builder')
  const [selectedEntryId, setSelectedEntryId] = useState(null)
  const [menuTitle, setMenuTitle] = useState('PXE Boot Menu')
  const [menuTimeout, setMenuTimeout] = useState(30000)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState(null)
  const [generatedScript, setGeneratedScript] = useState('')
  const [scriptWarnings, setScriptWarnings] = useState([])
  const [generatingScript, setGeneratingScript] = useState(false)
  const [entries, setEntries] = useState([
    // Starter menu with submenus
    {
      name: 'linux',
      title: 'Linux',
      entry_type: 'submenu',
      enabled: true,
      order: 1,
      parent: null,
    },
    {
      name: 'windows',
      title: 'Windows',
      entry_type: 'submenu',
      enabled: true,
      order: 2,
      parent: null,
    },
    {
      name: 'tools',
      title: 'Rescue & Tools',
      entry_type: 'submenu',
      enabled: true,
      order: 3,
      parent: null,
    },
  ])

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

  const generateScript = async () => {
    setGeneratingScript(true)

    try {
      const menuData = {
        title: menuTitle,
        timeout: menuTimeout,
        default_entry: null,
        entries: entries.map(entry => ({
          name: entry.name,
          title: entry.title,
          kernel: entry.kernel || null,
          initrd: entry.initrd || null,
          cmdline: entry.cmdline || '',
          description: entry.description || '',
          enabled: entry.enabled !== false,
          order: entry.order || 0,
          entry_type: entry.entry_type || 'boot',
          url: entry.url || null,
          boot_mode: entry.boot_mode || 'netboot',
          requires_iso: entry.requires_iso || false,
          requires_internet: entry.requires_internet || false,
          parent: entry.parent || null,
        })),
        header_text: '',
        footer_text: '',
        server_ip: 'localhost',
        http_port: 8000,
      }

      const response = await fetch('/api/ipxe/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(menuData),
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
      setGeneratedScript(`# Failed to generate: ${error.message}`)
      setScriptWarnings([])
    } finally {
      setGeneratingScript(false)
    }
  }

  const saveMenu = async () => {
    setSaving(true)
    setSaveMessage(null)

    try {
      // Convert entries to backend format
      const menuData = {
        title: menuTitle,
        timeout: menuTimeout,
        default_entry: null,
        entries: entries.map(entry => ({
          name: entry.name,
          title: entry.title,
          kernel: entry.kernel || null,
          initrd: entry.initrd || null,
          cmdline: entry.cmdline || '',
          description: entry.description || '',
          enabled: entry.enabled !== false,
          order: entry.order || 0,
          entry_type: entry.entry_type || 'boot',
          url: entry.url || null,
          boot_mode: entry.boot_mode || 'netboot',
          requires_iso: entry.requires_iso || false,
          requires_internet: entry.requires_internet || false,
          parent: entry.parent || null,
        })),
        header_text: '',
        footer_text: '',
        server_ip: 'localhost',
        http_port: 8000,
      }

      const response = await fetch('/api/ipxe/menu/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(menuData),
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
      // Clear message after 5 seconds
      setTimeout(() => setSaveMessage(null), 5000)
    }
  }

  // Auto-generate script when switching to preview tab
  useEffect(() => {
    if (activeTab === 'preview') {
      generateScript()
    }
  }, [activeTab, entries, menuTitle, menuTimeout])

  const selectedEntry = entries.find(e => e.name === selectedEntryId)

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
          <button className="btn btn-secondary">⚙️ Settings</button>
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
      <div className="main-layout">
        {/* Left Sidebar - Menu Tree */}
        <aside className="sidebar-left">
          <div className="sidebar-header">
            <h2>Menu Structure</h2>
          </div>
          <div className="sidebar-content">
            <MenuBuilder
              entries={entries}
              selectedEntryId={selectedEntryId}
              onSelectEntry={setSelectedEntryId}
              onAddEntry={addEntry}
              onUpdateEntry={updateEntry}
              onDeleteEntry={deleteEntry}
            />
          </div>
        </aside>

        {/* Center - Main Content Area */}
        <main className="main-content">
          {/* Tabs */}
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'builder' ? 'active' : ''}`}
              onClick={() => setActiveTab('builder')}
            >
              🏗️ Builder
            </button>
            <button
              className={`tab ${activeTab === 'assets' ? 'active' : ''}`}
              onClick={() => setActiveTab('assets')}
            >
              📦 Assets
            </button>
            <button
              className={`tab ${activeTab === 'dhcp' ? 'active' : ''}`}
              onClick={() => setActiveTab('dhcp')}
            >
              🌐 DHCP
            </button>
            <button
              className={`tab ${activeTab === 'preview' ? 'active' : ''}`}
              onClick={() => setActiveTab('preview')}
            >
              👁️ Preview
            </button>
            <button
              className={`tab ${activeTab === 'export' ? 'active' : ''}`}
              onClick={() => setActiveTab('export')}
            >
              💾 Export
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
                          <div key={key} className="action-card" style={{ borderColor: category.color }}>
                            <div className="action-icon">{category.icon}</div>
                            <div className="action-name">{category.name}</div>
                            <div className="action-description">{category.description}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'assets' && (
              <AssetManager />
            )}

            {activeTab === 'dhcp' && (
              <DHCPHelper />
            )}

            {activeTab === 'preview' && (
              <div className="preview-view">
                <div className="preview-header">
                  <h2>iPXE Script Preview</h2>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={generateScript}
                    disabled={generatingScript}
                  >
                    {generatingScript ? '⏳ Generating...' : '🔄 Refresh'}
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
            )}

            {activeTab === 'export' && (
              <div className="export-view">
                <h2>Export Menu</h2>
                <p>Export your menu configuration in various formats</p>
                <div className="export-options">
                  <button className="btn btn-primary">Download as JSON</button>
                  <button className="btn btn-primary">Download iPXE Script</button>
                  <button className="btn btn-secondary">Copy to Clipboard</button>
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Right Sidebar - Properties */}
        <aside className="sidebar-right">
          <div className="sidebar-header">
            <h2>Properties</h2>
          </div>
          <div className="sidebar-content">
            <PropertyPanel
              entry={selectedEntry}
              onUpdateEntry={updateEntry}
              entries={entries}
            />
          </div>
        </aside>
      </div>

      {/* Footer */}
      <footer className="app-footer">
        <div className="footer-left">
          <span>iPXE Station - Network Boot Made Easy</span>
        </div>
        <div className="footer-right">
          <span>Entries: {entries.length}</span>
          <span>•</span>
          <span>Enabled: {entries.filter(e => e.enabled).length}</span>
        </div>
      </footer>
    </div>
  )
}

export default App
