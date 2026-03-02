import { useState } from 'react'
import './MenuBuilder.css'

function MenuBuilder({ entries, selectedEntryId, onSelectEntry, onOpenWizard, onUpdateEntry, onDeleteEntry }) {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']))

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

  const handleMoveUp = (entry, e) => {
    e.stopPropagation()
    const siblings = entries.filter(s => s.parent === entry.parent).sort((a, b) => a.order - b.order)
    const idx = siblings.findIndex(s => s.name === entry.name)
    if (idx > 0) {
      const prev = siblings[idx - 1]
      onUpdateEntry(entry.name, { order: prev.order })
      onUpdateEntry(prev.name, { order: entry.order })
    }
  }

  const handleMoveDown = (entry, e) => {
    e.stopPropagation()
    const siblings = entries.filter(s => s.parent === entry.parent).sort((a, b) => a.order - b.order)
    const idx = siblings.findIndex(s => s.name === entry.name)
    if (idx < siblings.length - 1) {
      const next = siblings[idx + 1]
      onUpdateEntry(entry.name, { order: next.order })
      onUpdateEntry(next.name, { order: entry.order })
    }
  }

  const handleMoveTo = (entry, targetParent, e) => {
    e.stopPropagation()
    const newParent = targetParent === '' ? null : targetParent
    // Assign order at end of target group
    const targetSiblings = entries.filter(s => s.parent === newParent)
    const maxOrder = targetSiblings.length > 0
      ? Math.max(...targetSiblings.map(s => s.order)) + 1
      : 0
    onUpdateEntry(entry.name, { parent: newParent, order: maxOrder })
  }

  const handleDelete = (entry, e) => {
    e.stopPropagation()
    if (window.confirm(`Delete "${entry.title || entry.name}"?`)) {
      onDeleteEntry(entry.name)
    }
  }

  const renderEntry = (entry, level = 0) => {
    const isSelected = entry.name === selectedEntryId
    const isExpanded = expandedNodes.has(entry.name)
    const isSubmenu = entry.entry_type === 'submenu'
    const children = isSubmenu ? getChildEntries(entry.name) : []

    const siblings = entries.filter(s => s.parent === entry.parent).sort((a, b) => a.order - b.order)
    const idx = siblings.findIndex(s => s.name === entry.name)
    const canUp = idx > 0
    const canDown = idx < siblings.length - 1

    // Submenus this entry can move into (excluding itself and its own children)
    const moveTargets = submenus.filter(s => s.name !== entry.name)

    return (
      <div key={entry.name} className="tree-entry">
        <div
          className={`tree-node ${isSelected ? 'selected' : ''} ${!entry.enabled ? 'disabled' : ''}`}
          style={{ paddingLeft: `${level * 18 + 6}px` }}
          onClick={() => onSelectEntry(entry.name)}
        >
          {/* Expand toggle */}
          <span
            className="tree-toggle"
            onClick={isSubmenu ? (e) => toggleNode(entry.name, e) : undefined}
            style={{ visibility: isSubmenu ? 'visible' : 'hidden' }}
          >
            {isExpanded ? '▼' : '▶'}
          </span>

          <span className="tree-icon">{getEntryIcon(entry)}</span>
          <span className="tree-label">{entry.title || entry.name}</span>

          {!entry.enabled && <span className="badge badge-disabled">off</span>}

          {/* Inline controls — shown on hover */}
          <span className="tree-controls" onClick={e => e.stopPropagation()}>
            <button className="tree-btn" onClick={(e) => handleMoveUp(entry, e)} disabled={!canUp} title="Move up">↑</button>
            <button className="tree-btn" onClick={(e) => handleMoveDown(entry, e)} disabled={!canDown} title="Move down">↓</button>

            {/* Move-to dropdown */}
            <select
              className="tree-move-select"
              value={entry.parent || ''}
              onChange={(e) => handleMoveTo(entry, e.target.value, e)}
              title={`Move to submenu (${moveTargets.length} available)`}
            >
              <option value="">📁 root</option>
              {moveTargets.map(s => (
                <option key={s.name} value={s.name}>📂 {s.title || s.name}</option>
              ))}
            </select>

            <button className="tree-btn tree-btn-del" onClick={(e) => handleDelete(entry, e)} title="Delete">✕</button>
          </span>
        </div>

        {isSubmenu && isExpanded && (
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

  return (
    <div className="menu-builder">
      <div className="menu-tree">
        {rootEntries.length === 0 ? (
          <div className="empty-state">
            <p>No entries yet</p>
            <p className="text-sm text-muted">Click "Add Entry" to start</p>
          </div>
        ) : (
          rootEntries.map(entry => renderEntry(entry))
        )}
      </div>

      <div className="menu-actions">
        <button className="btn btn-primary btn-block" onClick={() => onOpenWizard()}>
          ➕ Add Entry
        </button>
      </div>
    </div>
  )
}

export default MenuBuilder
