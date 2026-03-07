import { useState } from 'react'
import './MenuBuilder.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

function MenuBuilder({
  entries,
  selectedEntryId,
  onSelectEntry,
  onOpenWizard,
  onUpdateEntry,
  onDeleteEntry,
  onDuplicateEntry,
  onSetEntriesEnabled,
}) {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']))
  const [pendingDelete, setPendingDelete] = useState(null) // entry object
  const [query, setQuery] = useState('')
  const [draggingEntryName, setDraggingEntryName] = useState(null)
  const [dropTargetKey, setDropTargetKey] = useState(null)

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

  const getSubtreeNames = (entryName) => {
    const names = new Set()
    const stack = [entryName]
    while (stack.length > 0) {
      const current = stack.pop()
      if (names.has(current)) continue
      names.add(current)
      const children = entries.filter((entry) => entry.parent === current)
      children.forEach((child) => stack.push(child.name))
    }
    return names
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

  const handleDuplicate = (entry) => {
    const duplicated = onDuplicateEntry?.(entry.name)
    if (duplicated) onSelectEntry(duplicated)
  }

  const canMoveToParent = (entryName, targetParent) => {
    if (entryName === targetParent) return false
    if (!targetParent) return true
    const descendants = getDescendantNames(entryName)
    return !descendants.has(targetParent)
  }

  const moveEntryToParent = (entryName, targetParent) => {
    const newParent = targetParent || null
    const current = entries.find((entry) => entry.name === entryName)
    if (!current) return
    if (!canMoveToParent(entryName, newParent)) return
    if (current.parent === newParent) return

    const targetSiblings = entries.filter((entry) => entry.parent === newParent)
    const maxOrder = targetSiblings.length > 0
      ? Math.max(...targetSiblings.map((entry) => entry.order)) + 1
      : 0
    onUpdateEntry(entryName, { parent: newParent, order: maxOrder })
  }

  const handleDragStart = (entryName) => {
    setDraggingEntryName(entryName)
  }

  const handleDragEnd = () => {
    setDraggingEntryName(null)
    setDropTargetKey(null)
  }

  const handleDropToParent = (targetParentName, e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!draggingEntryName) return
    moveEntryToParent(draggingEntryName, targetParentName)
    setDropTargetKey(null)
  }

  const getDropPlacement = (entry, event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const relativeY = event.clientY - rect.top
    const ratio = rect.height > 0 ? (relativeY / rect.height) : 0.5

    if (entry.entry_type === 'submenu') {
      if (ratio < 0.3) return 'before'
      if (ratio > 0.7) return 'after'
      return 'inside'
    }
    return ratio < 0.5 ? 'before' : 'after'
  }

  const moveEntryRelativeToTarget = (entryName, targetName, place = 'after') => {
    const source = entries.find((entry) => entry.name === entryName)
    const target = entries.find((entry) => entry.name === targetName)
    if (!source || !target || source.name === target.name) return

    const targetParent = target.parent || null
    if (!canMoveToParent(entryName, targetParent)) return

    const destinationSiblings = entries
      .filter((entry) => entry.parent === targetParent && entry.name !== entryName)
      .sort((a, b) => a.order - b.order)

    const targetIndex = destinationSiblings.findIndex((entry) => entry.name === targetName)
    if (targetIndex < 0) return

    const sourceWithParent = { ...source, parent: targetParent }
    const insertIndex = place === 'before' ? targetIndex : targetIndex + 1
    const reordered = [
      ...destinationSiblings.slice(0, insertIndex),
      sourceWithParent,
      ...destinationSiblings.slice(insertIndex),
    ]

    reordered.forEach((entry, index) => {
      const prev = entries.find((item) => item.name === entry.name)
      if (!prev) return
      if (prev.order !== index || prev.parent !== entry.parent) {
        onUpdateEntry(entry.name, { parent: entry.parent, order: index })
      }
    })
  }

  const handleDropOnEntry = (targetEntry, e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!draggingEntryName) return
    const placement = getDropPlacement(targetEntry, e)
    if (placement === 'inside' && targetEntry.entry_type === 'submenu') {
      moveEntryToParent(draggingEntryName, targetEntry.name)
    } else {
      moveEntryRelativeToTarget(draggingEntryName, targetEntry.name, placement)
    }
    setDropTargetKey(null)
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
    const insideDropKey = `inside-zone:${entry.name}`

    return (
      <div key={entry.name} className="tree-entry">
        <div
          className={`tree-node ${isSelected ? 'selected' : ''} ${!entry.enabled ? 'disabled' : ''}`}
          style={{ paddingLeft: `${level * 18 + 6}px` }}
          onClick={() => onSelectEntry(entry.name)}
          draggable
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = 'move'
            e.dataTransfer.setData('text/plain', entry.name)
            handleDragStart(entry.name)
          }}
          onDragEnd={handleDragEnd}
          onDragOver={(e) => {
            if (!draggingEntryName) return
            if (draggingEntryName === entry.name) return
            const placement = getDropPlacement(entry, e)
            const targetParent = placement === 'inside' ? entry.name : (entry.parent || null)
            if (!canMoveToParent(draggingEntryName, targetParent)) return
            e.preventDefault()
            e.dataTransfer.dropEffect = 'move'
            setDropTargetKey(`${placement}:${entry.name}`)
          }}
          onDragLeave={() => {
            if (
              dropTargetKey === `before:${entry.name}` ||
              dropTargetKey === `inside:${entry.name}` ||
              dropTargetKey === `after:${entry.name}`
            ) {
              setDropTargetKey(null)
            }
          }}
          onDrop={(e) => handleDropOnEntry(entry, e)}
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
            className={`tree-select-btn ${
              dropTargetKey === `before:${entry.name}` ? 'drop-target-before' : ''
            } ${
              dropTargetKey === `inside:${entry.name}` ? 'drop-target-inside' : ''
            } ${
              dropTargetKey === `after:${entry.name}` ? 'drop-target-after' : ''
            }`}
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
            <div
              className={`tree-inside-drop-zone ${dropTargetKey === insideDropKey ? 'active' : ''}`}
              onDragOver={(e) => {
                if (!draggingEntryName) return
                if (!canMoveToParent(draggingEntryName, entry.name)) return
                e.preventDefault()
                e.stopPropagation()
                e.dataTransfer.dropEffect = 'move'
                setDropTargetKey(insideDropKey)
              }}
              onDragLeave={() => {
                if (dropTargetKey === insideDropKey) setDropTargetKey(null)
              }}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                if (!draggingEntryName) return
                moveEntryToParent(draggingEntryName, entry.name)
                setDropTargetKey(null)
              }}
            >
              Drop inside "{entry.title || entry.name}"
            </div>
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
  const selectedSubtreeNames = selectedEntry ? Array.from(getSubtreeNames(selectedEntry.name)) : []
  const hasEntries = entries.length > 0

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
            onClick={() => onSetEntriesEnabled(entries.map((entry) => entry.name), true)}
            disabled={!hasEntries}
            title="Enable all entries"
          >
            Enable all
          </button>
          <button
            type="button"
            className="menu-mini-btn"
            onClick={() => onSetEntriesEnabled(entries.map((entry) => entry.name), false)}
            disabled={!hasEntries}
            title="Disable all entries"
          >
            Disable all
          </button>
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
        <div
          className={`tree-root-drop ${dropTargetKey === '__root__' ? 'active' : ''}`}
          onDragOver={(e) => {
            if (!draggingEntryName) return
            if (!canMoveToParent(draggingEntryName, null)) return
            e.preventDefault()
            e.dataTransfer.dropEffect = 'move'
            setDropTargetKey('__root__')
          }}
          onDragLeave={() => {
            if (dropTargetKey === '__root__') setDropTargetKey(null)
          }}
          onDrop={(e) => handleDropToParent(null, e)}
        >
          Drag here to move entry to root
        </div>
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
                onClick={() => handleDuplicate(selectedEntry)}
                title="Duplicate selected entry"
              >
                ⎘ Duplicate
              </button>
              <button
                className="tree-btn"
                onClick={() => onSetEntriesEnabled([selectedEntry.name], true)}
                disabled={selectedEntry.enabled}
                title="Enable selected entry"
              >
                Enable
              </button>
              <button
                className="tree-btn"
                onClick={() => onSetEntriesEnabled([selectedEntry.name], false)}
                disabled={!selectedEntry.enabled}
                title="Disable selected entry"
              >
                Disable
              </button>
              <button
                className="tree-btn"
                onClick={() => onSetEntriesEnabled(selectedSubtreeNames, true)}
                disabled={selectedSubtreeNames.length === 0}
                title="Enable selected entry and its children"
              >
                Enable subtree
              </button>
              <button
                className="tree-btn"
                onClick={() => onSetEntriesEnabled(selectedSubtreeNames, false)}
                disabled={selectedSubtreeNames.length === 0}
                title="Disable selected entry and its children"
              >
                Disable subtree
              </button>
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
