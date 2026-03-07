import { useState } from 'react'
import './MenuBuilder.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

function MenuBuilder({ entries, selectedEntryId, onSelectEntry, onOpenWizard, onUpdateEntry, onDeleteEntry }) {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']))
  const [pendingDelete, setPendingDelete] = useState(null) // entry object
  const [query, setQuery] = useState('')

  const toggleNode = (nodeName, e) => {
    e.stopPropagation()
    setExpandedNodes(prev => {
      const next = new Set(prev)
      if (next.has(nodeName)) next.delete(nodeName)
      else next.add(nodeName)
      return next
    })
  }

  const getEntryIcon = (entry) => {
    if (entry.entry_type === 'submenu') return '📂'
    if (entry.entry_type === 'boot') {
      const mode = entry.boot_mode
      if (mode === 'live') return '💿'
      if (mode === 'rescue') return '🛠️'
      if (mode === 'netboot') return '🌐'
      return '🐧'
    }
    if (entry.entry_type === 'chain') return '🔗'
    if (entry.entry_type === 'separator') return '—'
    return '⚙️'
  }

  const getChildEntries = (parentName) =>
    entries.filter(e => e.parent === parentName).sort((a, b) => a.order - b.order)

  const submenus = entries.filter(e => e.entry_type === 'submenu')
  const queryNorm = query.trim().toLowerCase()

  const matchesQuery = (entry) => {
    if (!queryNorm) return true
    const haystack = `${entry.title || ''} ${entry.name || ''}`.toLowerCase()
    return haystack.includes(queryNorm)
  }

  const getDescendantNames = (entryName) => {
    const descendants = new Set()
    const stack = [entryName]

    while (stack.length > 0) {
      const current = stack.pop()
      const children = entries.filter(e => e.parent === current && e.entry_type === 'submenu')
      children.forEach((child) => {
        if (!descendants.has(child.name)) {
          descendants.add(child.name)
          stack.push(child.name)
        }
      })
    }

    return descendants
  }

  const handleMoveUp = (entry) => {
    const siblings = entries.filter(s => s.parent === entry.parent).sort((a, b) => a.order - b.order)
    const idx = siblings.findIndex(s => s.name === entry.name)
    if (idx > 0) {
      const prev = siblings[idx - 1]
      onUpdateEntry(entry.name, { order: prev.order })
      onUpdateEntry(prev.name, { order: entry.order })
    }
  }

  const handleMoveDown = (entry) => {
    const siblings = entries.filter(s => s.parent === entry.parent).sort((a, b) => a.order - b.order)
    const idx = siblings.findIndex(s => s.name === entry.name)
    if (idx < siblings.length - 1) {
      const next = siblings[idx + 1]
      onUpdateEntry(entry.name, { order: next.order })
      onUpdateEntry(next.name, { order: entry.order })
    }
  }

  const handleMoveTo = (entry, targetParent) => {
    const newParent = targetParent === '' ? null : targetParent
    // Assign order at end of target group
    const targetSiblings = entries.filter(s => s.parent === newParent)
    const maxOrder = targetSiblings.length > 0
      ? Math.max(...targetSiblings.map(s => s.order)) + 1
      : 0
    onUpdateEntry(entry.name, { parent: newParent, order: maxOrder })
  }

  const handleDelete = (entry) => {
    setPendingDelete(entry)
  }

  const subtreeMatchesQuery = (entry) => {
    if (matchesQuery(entry)) return true
    if (entry.entry_type !== 'submenu') return false
    const children = getChildEntries(entry.name)
    return children.some(subtreeMatchesQuery)
  }

  const renderEntry = (entry, level = 0) => {
    if (!subtreeMatchesQuery(entry)) return null

    const isSelected = entry.name === selectedEntryId
    const isExpanded = expandedNodes.has(entry.name)
    const isSubmenu = entry.entry_type === 'submenu'
    const children = isSubmenu ? getChildEntries(entry.name) : []
    const effectiveExpanded = queryNorm ? true : isExpanded

    return (
      <div key={entry.name} className="tree-entry">
        <div
          className={`tree-node ${isSelected ? 'selected' : ''} ${!entry.enabled ? 'disabled' : ''}`}
          style={{ paddingLeft: `${level * 18 + 6}px` }}
          onClick={() => onSelectEntry(entry.name)}
        >
          <button
            type="button"
            className={`tree-toggle ${isSubmenu ? 'tree-toggle-btn' : 'tree-toggle-placeholder'}`}
            onClick={isSubmenu ? (e) => toggleNode(entry.name, e) : undefined}
            aria-label={isSubmenu ? `${effectiveExpanded ? 'Collapse' : 'Expand'} ${entry.title || entry.name}` : undefined}
            aria-expanded={isSubmenu ? effectiveExpanded : undefined}
            tabIndex={isSubmenu ? 0 : -1}
          >
            {isSubmenu ? (effectiveExpanded ? '▼' : '▶') : ''}
          </button>

          <button
            type="button"
            className="tree-select-btn"
            onClick={() => onSelectEntry(entry.name)}
            aria-current={isSelected ? 'true' : undefined}
            title={entry.title || entry.name}
          >
            <span className="tree-icon">{getEntryIcon(entry)}</span>
            <span className="tree-label">{entry.title || entry.name}</span>

            {!entry.enabled && <span className="badge badge-disabled">off</span>}
          </button>
        </div>

        {isSubmenu && effectiveExpanded && (
          <div className="tree-children">
            {children.length > 0
              ? children.map(child => renderEntry(child, level + 1))
              : <div className="tree-empty-submenu" style={{ paddingLeft: `${(level + 1) * 18 + 6}px` }}>empty</div>
            }
          </div>
        )}
      </div>
    )
  }

  const rootEntries = entries.filter(e => !e.parent).sort((a, b) => a.order - b.order)
  const visibleRootEntries = rootEntries.filter(subtreeMatchesQuery)
  const selectedEntry = entries.find((entry) => entry.name === selectedEntryId)
  const selectedSiblings = selectedEntry
    ? entries.filter((entry) => entry.parent === selectedEntry.parent).sort((a, b) => a.order - b.order)
    : []
  const selectedIndex = selectedEntry
    ? selectedSiblings.findIndex((entry) => entry.name === selectedEntry.name)
    : -1
  const canMoveUp = selectedEntry && selectedIndex > 0
  const canMoveDown = selectedEntry && selectedIndex < selectedSiblings.length - 1
  const selectedDescendants = selectedEntry ? getDescendantNames(selectedEntry.name) : new Set()
  const moveTargets = selectedEntry
    ? submenus.filter((entry) => entry.name !== selectedEntry.name && !selectedDescendants.has(entry.name))
    : []

  return (
    <div className="menu-builder">
      <div className="menu-toolbar">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="menu-search"
          placeholder="Search entries..."
          aria-label="Search menu entries"
        />
        <div className="menu-toolbar-actions">
          <button
            type="button"
            className="menu-mini-btn"
            onClick={() => setExpandedNodes(new Set(submenus.map((s) => s.name)))}
            title="Expand all submenus"
          >
            Expand
          </button>
          <button
            type="button"
            className="menu-mini-btn"
            onClick={() => setExpandedNodes(new Set())}
            title="Collapse all submenus"
          >
            Collapse
          </button>
        </div>
      </div>

      <div className="menu-tree">
        {rootEntries.length === 0 ? (
          <div className="empty-state">
            <p>No entries yet</p>
            <p className="text-sm text-muted">Click "Add Entry" to start</p>
          </div>
        ) : visibleRootEntries.length === 0 ? (
          <div className="empty-state">
            <p>No matches</p>
            <p className="text-sm text-muted">Try another search query</p>
          </div>
        ) : (
          visibleRootEntries.map(entry => renderEntry(entry))
        )}
      </div>

      <div className="menu-actions">
        {selectedEntry && (
          <div className="selected-actions">
            <div className="selected-actions-head">
              <strong>{selectedEntry.title || selectedEntry.name}</strong>
              <small>{selectedEntry.name}</small>
            </div>
            <div className="selected-actions-row">
              <button
                className="tree-btn"
                onClick={() => handleMoveUp(selectedEntry)}
                disabled={!canMoveUp}
                title="Move selected entry up"
              >
                ↑ Up
              </button>
              <button
                className="tree-btn"
                onClick={() => handleMoveDown(selectedEntry)}
                disabled={!canMoveDown}
                title="Move selected entry down"
              >
                ↓ Down
              </button>
              <select
                className="tree-move-select"
                value={selectedEntry.parent || ''}
                onChange={(e) => handleMoveTo(selectedEntry, e.target.value)}
                title={`Move to submenu (${moveTargets.length} available)`}
                aria-label={`Move ${selectedEntry.title || selectedEntry.name} to submenu`}
              >
                <option value="">📁 root</option>
                {moveTargets.map((entry) => (
                  <option key={entry.name} value={entry.name}>📂 {entry.title || entry.name}</option>
                ))}
              </select>
              <button
                className="tree-btn tree-btn-del"
                onClick={() => handleDelete(selectedEntry)}
                title="Delete selected entry"
              >
                ✕ Delete
              </button>
            </div>
          </div>
        )}
        <button className="btn btn-primary btn-block" onClick={() => onOpenWizard()}>
          ➕ Add Entry
        </button>
      </div>

      <ConfirmDialog
        isOpen={!!pendingDelete}
        title="Delete entry?"
        message={pendingDelete ? `"${pendingDelete.title || pendingDelete.name}" will be removed from the menu.` : ''}
        confirmLabel="Delete"
        danger
        onConfirm={() => {
          onDeleteEntry(pendingDelete.name)
          setPendingDelete(null)
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}

export default MenuBuilder
