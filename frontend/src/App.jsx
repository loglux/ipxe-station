import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'

// Placeholder components - we'll create these next
import BuilderCards from './components/BuilderCards/BuilderCards'
import PropertyPanel from './components/PropertyPanel/PropertyPanel'
import AssetManager from './components/AssetManager/AssetManager'
import DHCPHelper from './components/DHCPHelper/DHCPHelper'
import AddEntryWizard from './components/Wizard/AddEntryWizard'
import Settings from './components/Settings/Settings'
import Monitoring from './components/Monitoring/Monitoring'
import BootFiles from './components/BootFiles/BootFiles'
import ConfirmDialog from './components/ConfirmDialog/ConfirmDialog'

const VALID_TABS = ['builder', 'assets', 'dhcp', 'boot', 'monitoring']

function App() {
  const githubProfileUrl = import.meta.env.VITE_GITHUB_PROFILE_URL || 'https://github.com/loglux'
  const [activeTab, setActiveTab] = useState(() => {
    const saved = window.location.hash.slice(1)
    return VALID_TABS.includes(saved) ? saved : 'builder'
  })
  const switchTab = (tab) => {
    setActiveTab(tab)
    window.location.hash = tab
    if (tab !== 'builder') setSelectedEntryId(null)
    if (tab !== 'builder') setSelectedEntryId(null)
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
  const [previewExpanded, setPreviewExpanded] = useState(false)
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

  // Keep active tab in sync when hash changes outside React tab clicks
  useEffect(() => {
    const onHashChange = () => {
      const hashTab = window.location.hash.slice(1)
      if (VALID_TABS.includes(hashTab)) {
        setActiveTab(hashTab)
        if (hashTab !== 'builder') setSelectedEntryId(null)
        if (hashTab !== 'builder') setSelectedEntryId(null)
      }
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])


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
    // If name changed while this entry is selected, follow the rename
    if ('name' in updates && selectedEntryId === entryName) {
      setSelectedEntryId(updates.name || entryName)
    }
  }

  const moveEntry = useCallback((entryName, newParent, insertIndex) => {
    setEntries(prev => {
      const entry = prev.find(e => e.name === entryName)
      if (!entry) return prev
      const oldParent = entry.parent ?? null
      const newParentNorm = newParent ?? null

      // Re-order new siblings (including moved entry)
      const newSiblings = prev
        .filter(e => (e.parent ?? null) === newParentNorm && e.name !== entryName)
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      newSiblings.splice(Math.min(insertIndex, newSiblings.length), 0, entry)
      const newOrderMap = new Map(newSiblings.map((e, i) => [e.name, i]))

      // Re-order old siblings if parent changed
      const oldOrderMap = new Map()
      if (oldParent !== newParentNorm) {
        prev
          .filter(e => (e.parent ?? null) === oldParent && e.name !== entryName)
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
          .forEach((e, i) => oldOrderMap.set(e.name, i))
      }

      return prev.map(e => {
        if (e.name === entryName) return { ...e, parent: newParentNorm, order: newOrderMap.get(entryName) ?? insertIndex }
        if (newOrderMap.has(e.name)) return { ...e, order: newOrderMap.get(e.name) }
        if (oldOrderMap.has(e.name)) return { ...e, order: oldOrderMap.get(e.name) }
        return e
      })
    })
  }, [])

  const deleteEntry = (entryName) => {
    setEntries(prev => prev.filter(e => e.name !== entryName))
    if (selectedEntryId === entryName) {
      setSelectedEntryId(null)
    }
  }

  const duplicateEntry = (entryName) => {
    let duplicatedName = null

    setEntries((prev) => {
      const source = prev.find((entry) => entry.name === entryName)
      if (!source) return prev

      const usedNames = new Set(prev.map((entry) => entry.name))
      const baseName = `${source.name}_copy`
      let candidate = baseName
      let index = 2
      while (usedNames.has(candidate)) {
        candidate = `${baseName}${index}`
        index += 1
      }

      duplicatedName = candidate
      const siblingOrders = prev
        .filter((entry) => entry.parent === source.parent)
        .map((entry) => entry.order)
      const maxOrder = siblingOrders.length > 0 ? Math.max(...siblingOrders) : -1

      const duplicatedEntry = {
        ...source,
        name: candidate,
        title: source.title ? `${source.title} (copy)` : `${source.name} (copy)`,
        order: maxOrder + 1,
      }

      return [...prev, duplicatedEntry]
    })

    if (duplicatedName) {
      setSelectedEntryId(duplicatedName)
    }
    return duplicatedName
  }

  const setEntriesEnabled = (entryNames, enabled) => {
    const targets = new Set(entryNames)
    setEntries((prev) => prev.map((entry) => (
      targets.has(entry.name) ? { ...entry, enabled } : entry
    )))
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

  // Resizable split between BuilderCards and PropertyPanel
  const [builderSplit, setBuilderSplit] = useState(58) // % for left panel
  const builderMainRef = useRef(null)
  const onDividerMouseDown = useCallback((e) => {
    e.preventDefault()
    const onMove = (ev) => {
      if (!builderMainRef.current) return
      const rect = builderMainRef.current.getBoundingClientRect()
      const pct = ((ev.clientX - rect.left) / rect.width) * 100
      setBuilderSplit(Math.min(82, Math.max(22, pct)))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [])

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
          <h1>iPXE Station</h1>
        </div>
        <div className="header-right">
          {saveMessage && (
            <div className={`save-message ${saveMessage.type}`} aria-live="polite" role="status">
              {saveMessage.text}
            </div>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setDeleteConfirmOpen(true)}
            disabled={saving}
            title="Delete entire menu (boot.ipxe and menu.json)"
            style={{ color: 'var(--color-danger)' }}
          >
            🗑️ Delete
          </button>
          <button className="btn btn-secondary" onClick={() => setSettingsOpen(true)}>⚙️ Settings</button>
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
      <div className="main-layout full-width">

        {/* Center - Main Content Area */}
        <main className="main-content">
          {/* Tabs */}
          <div className="tabs" role="tablist" aria-label="Main navigation">
            <button
              role="tab"
              className={`tab ${activeTab === 'builder' ? 'active' : ''}`}
              onClick={() => { switchTab('builder'); setSelectedEntryId(null) }}
              aria-selected={activeTab === 'builder'}
              aria-controls="tab-panel-builder"
            >
              🏗️ Builder
            </button>
            <button
              role="tab"
              className={`tab ${activeTab === 'assets' ? 'active' : ''}`}
              onClick={() => switchTab('assets')}
              aria-selected={activeTab === 'assets'}
              aria-controls="tab-panel-assets"
            >
              📦 Assets
            </button>
            <button
              role="tab"
              className={`tab ${activeTab === 'dhcp' ? 'active' : ''}`}
              onClick={() => switchTab('dhcp')}
              aria-selected={activeTab === 'dhcp'}
              aria-controls="tab-panel-dhcp"
            >
              🌐 DHCP
            </button>
            <button
              role="tab"
              className={`tab ${activeTab === 'boot' ? 'active' : ''}`}
              onClick={() => switchTab('boot')}
              aria-selected={activeTab === 'boot'}
              aria-controls="tab-panel-boot"
            >
              🚀 Boot Files
            </button>
            <button
              role="tab"
              className={`tab ${activeTab === 'monitoring' ? 'active' : ''}`}
              onClick={() => switchTab('monitoring')}
              aria-selected={activeTab === 'monitoring'}
              aria-controls="tab-panel-monitoring"
            >
              📊 Monitoring
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'builder' && (
              <div className="builder-view builder-tab-panel" role="tabpanel" id="tab-panel-builder">
                <div className="builder-main" ref={builderMainRef}>
                  <div
                    className="builder-cards-pane"
                    style={selectedEntry ? { flex: `0 0 ${builderSplit}%` } : undefined}
                  >
                    <BuilderCards
                      entries={entries}
                      selectedEntryId={selectedEntryId}
                      onSelectEntry={setSelectedEntryId}
                      onOpenWizard={openWizard}
                      onUpdateEntry={updateEntry}
                      onDeleteEntry={deleteEntry}
                      onDuplicateEntry={duplicateEntry}
                      onSetEntriesEnabled={setEntriesEnabled}
                      onMoveEntry={moveEntry}
                    />
                  </div>
                  {selectedEntry && (
                    <>
                      <div
                        className="builder-divider"
                        onMouseDown={onDividerMouseDown}
                        title="Drag to resize"
                      />
                      <div className="builder-property-pane">
                        <PropertyPanel
                          entry={selectedEntry}
                          onUpdateEntry={updateEntry}
                          onDeleteEntry={deleteEntry}
                          entries={entries}
                        />
                      </div>
                    </>
                  )}
                </div>

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
                        onClick={() => setPreviewExpanded(v => !v)}
                        title={previewExpanded ? 'Collapse script view' : 'Expand to show full script'}
                      >
                        {previewExpanded ? '⤡ Collapse' : '⤢ Expand'}
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
                    <pre className={`code-preview${previewExpanded ? ' code-preview-full' : ''}`}>
                      {generatingScript ? '# Generating script...' : (generatedScript || '# No script generated yet')}
                    </pre>
                  </div>
                </details>
              </div>
            )}

            {activeTab === 'assets' && <div role="tabpanel" id="tab-panel-assets"><AssetManager /></div>}
            {activeTab === 'dhcp' && <div role="tabpanel" id="tab-panel-dhcp"><DHCPHelper settingsVersion={settingsVersion} /></div>}
            {activeTab === 'boot' && <div role="tabpanel" id="tab-panel-boot"><BootFiles /></div>}
            {activeTab === 'monitoring' && <div role="tabpanel" id="tab-panel-monitoring" className="monitoring-tab-panel"><Monitoring /></div>}
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
