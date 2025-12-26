import { useState, useEffect } from 'react'
import './App.css'
import { CATEGORIES } from './data/scenarios'

// Placeholder components - we'll create these next
import MenuBuilder from './components/MenuBuilder/MenuBuilder'
import PropertyPanel from './components/PropertyPanel/PropertyPanel'
import AssetManager from './components/AssetManager/AssetManager'

function App() {
  const [activeTab, setActiveTab] = useState('builder')
  const [selectedEntryId, setSelectedEntryId] = useState(null)
  const [menuTitle, setMenuTitle] = useState('PXE Boot Menu')
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
          <button className="btn btn-secondary">⚙️ Settings</button>
          <button className="btn btn-primary">💾 Save Menu</button>
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
              </div>
            )}

            {activeTab === 'assets' && (
              <AssetManager />
            )}

            {activeTab === 'preview' && (
              <div className="preview-view">
                <h2>iPXE Script Preview</h2>
                <pre className="code-preview">
                  {`#!ipxe

:start
menu ${menuTitle}
${entries.map(e => `item ${e.name} ${e.title}`).join('\n')}
choose selected && goto \${selected}

${entries.map(e => `
:${e.name}
${e.entry_type === 'boot' && e.kernel ? `kernel ${e.kernel}` : ''}
${e.entry_type === 'boot' && e.initrd ? `initrd ${e.initrd}` : ''}
${e.entry_type === 'boot' ? 'boot' : ''}
${e.entry_type === 'action' ? e.cmdline || '' : ''}
`).join('\n')}
`}
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
