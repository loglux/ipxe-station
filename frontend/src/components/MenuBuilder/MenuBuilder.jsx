import { useState } from 'react'
import './MenuBuilder.css'

function MenuBuilder({ entries, selectedEntryId, onSelectEntry, onAddEntry, onUpdateEntry, onDeleteEntry }) {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']))

  const toggleNode = (nodeName) => {
    setExpandedNodes(prev => {
      const next = new Set(prev)
      if (next.has(nodeName)) {
        next.delete(nodeName)
      } else {
        next.add(nodeName)
      }
      return next
    })
  }

  const getEntryIcon = (entry) => {
    if (entry.entry_type === 'submenu') return '📂'
    if (entry.entry_type === 'boot') return '🐧'
    if (entry.entry_type === 'action') return '⚙️'
    if (entry.entry_type === 'chain') return '🔗'
    if (entry.entry_type === 'separator') return '—'
    return '📄'
  }

  const getChildEntries = (parentName) => {
    return entries
      .filter(e => e.parent === parentName)
      .sort((a, b) => a.order - b.order)
  }

  const renderEntry = (entry, level = 0) => {
    const isSelected = entry.name === selectedEntryId
    const isExpanded = expandedNodes.has(entry.name)
    const hasChildren = entry.entry_type === 'submenu'
    const children = hasChildren ? getChildEntries(entry.name) : []

    return (
      <div key={entry.name} className="tree-entry">
        <div
          className={`tree-node ${isSelected ? 'selected' : ''}`}
          style={{ paddingLeft: `${level * 20 + 8}px` }}
          onClick={() => onSelectEntry(entry.name)}
        >
          {hasChildren && (
            <span
              className="tree-toggle"
              onClick={(e) => {
                e.stopPropagation()
                toggleNode(entry.name)
              }}
            >
              {isExpanded ? '▼' : '▶'}
            </span>
          )}
          {!hasChildren && <span className="tree-toggle-placeholder"></span>}

          <span className="tree-icon">{getEntryIcon(entry)}</span>
          <span className="tree-label">{entry.title || entry.name}</span>

          {!entry.enabled && <span className="badge badge-disabled">Disabled</span>}
        </div>

        {hasChildren && isExpanded && children.length > 0 && (
          <div className="tree-children">
            {children.map(child => renderEntry(child, level + 1))}
          </div>
        )}
      </div>
    )
  }

  const rootEntries = entries.filter(e => !e.parent || e.parent === null)
    .sort((a, b) => a.order - b.order)

  return (
    <div className="menu-builder">
      <div className="menu-tree">
        {rootEntries.length === 0 && (
          <div className="empty-state">
            <p>No entries yet</p>
            <p className="text-sm text-muted">Click "Add Entry" to start building your menu</p>
          </div>
        )}

        {rootEntries.map(entry => renderEntry(entry))}
      </div>

      <div className="menu-actions">
        <button className="btn btn-primary btn-block" onClick={() => alert('Add Entry wizard - coming soon!')}>
          ➕ Add Entry
        </button>
      </div>
    </div>
  )
}

export default MenuBuilder
