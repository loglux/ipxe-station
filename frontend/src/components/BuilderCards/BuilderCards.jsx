import { useState, useMemo, useEffect, useRef } from 'react'
import './BuilderCards.css'

export default function BuilderCards({
  entries,
  selectedEntryId,
  onSelectEntry,
  onOpenWizard,
  onUpdateEntry,
  onDeleteEntry,
  onDuplicateEntry,
  onSetEntriesEnabled,
  onMoveEntry,
}) {
  const [expanded, setExpanded] = useState(() => new Set())
  const [query, setQuery] = useState('')
  const autoExpandedRef = useRef(false)

  // Drag & drop state
  const [dragging, setDragging] = useState(null)           // name of dragged entry (for visual)
  const [dragOver, setDragOver] = useState(null)           // { name, pos: 'before'|'after'|'into' }
  const draggingRef = useRef(null)                         // ref for use inside event handlers (no stale closure)
  const dragCounterRef = useRef({})                        // per-entry enter/leave counter

  // Auto-expand all root submenus once entries are first loaded
  useEffect(() => {
    if (autoExpandedRef.current || entries.length === 0) return
    autoExpandedRef.current = true
    const roots = entries
      .filter(e => !e.parent && e.entry_type === 'submenu')
      .map(e => e.name)
    setExpanded(new Set(roots))
  }, [entries])

  // Expand ancestors of selected entry
  useEffect(() => {
    if (!selectedEntryId) return
    setExpanded(prev => {
      const next = new Set(prev)
      let cur = entries.find(e => e.name === selectedEntryId)
      while (cur?.parent) {
        next.add(cur.parent)
        cur = entries.find(e => e.name === cur.parent)
      }
      return next
    })
  }, [selectedEntryId, entries])

  // Scroll selected card into view after layout settles (PropertyPanel appears → pane resizes)
  useEffect(() => {
    if (!selectedEntryId) return
    const timer = setTimeout(() => {
      const el = document.querySelector(`[data-entry-name="${selectedEntryId}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 200)
    return () => clearTimeout(timer)
  }, [selectedEntryId])

  const getChildren = (parentName) =>
    entries
      .filter(e => e.parent === parentName)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))

  const rootEntries = useMemo(
    () => entries.filter(e => !e.parent).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [entries]
  )

  const matchesQuery = (entry) => {
    if (!query) return true
    const q = query.toLowerCase()
    return (
      entry.name?.toLowerCase().includes(q) ||
      entry.title?.toLowerCase().includes(q) ||
      entry.kernel?.toLowerCase().includes(q)
    )
  }

  const toggleExpand = (name, e) => {
    e.stopPropagation()
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  // ── Drag & Drop handlers ──────────────────────────────────────────────────

  const handleDragStart = (e, entry) => {
    draggingRef.current = entry.name
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', entry.name)
    // Delay state update — immediate setState in dragstart cancels the drag in React
    setTimeout(() => setDragging(entry.name), 0)
  }

  const handleDragEnd = () => {
    draggingRef.current = null
    setDragging(null)
    setDragOver(null)
    dragCounterRef.current = {}
  }

  const handleDragOver = (e, entry) => {
    e.preventDefault()
    e.stopPropagation()
    const currentDragging = draggingRef.current || e.dataTransfer.getData('text/plain')
    if (!currentDragging || currentDragging === entry.name) return
    e.dataTransfer.dropEffect = 'move'

    const draggedEntry = entries.find(en => en.name === currentDragging)
    if (!draggedEntry) return

    const rect = e.currentTarget.getBoundingClientRect()

    // Submenus: top 30% = before, bottom 30% = after, middle = into
    // But don't allow dragging a submenu INTO another submenu
    if (entry.entry_type === 'submenu' && draggedEntry.entry_type !== 'submenu') {
      const relY = (e.clientY - rect.top) / rect.height
      const pos = relY < 0.3 ? 'before' : relY > 0.7 ? 'after' : 'into'
      setDragOver({ name: entry.name, pos })
    } else {
      const midY = rect.top + rect.height / 2
      setDragOver({ name: entry.name, pos: e.clientY < midY ? 'before' : 'after' })
    }
  }

  const handleDragEnter = (e, entryName) => {
    e.preventDefault()
    dragCounterRef.current[entryName] = (dragCounterRef.current[entryName] || 0) + 1
  }

  const handleDragLeave = (e, entryName) => {
    dragCounterRef.current[entryName] = (dragCounterRef.current[entryName] || 1) - 1
    if (dragCounterRef.current[entryName] <= 0) {
      dragCounterRef.current[entryName] = 0
      setDragOver(prev => (prev?.name === entryName ? null : prev))
    }
  }

  const handleDrop = (e, targetEntry) => {
    e.preventDefault()
    e.stopPropagation()
    const draggedName = draggingRef.current || e.dataTransfer.getData('text/plain')
    if (!draggedName || draggedName === targetEntry.name) {
      setDragging(null)
      setDragOver(null)
      return
    }

    const pos = dragOver?.name === targetEntry.name ? dragOver.pos : 'after'

    if (pos === 'into' && targetEntry.entry_type === 'submenu') {
      // Move into submenu as last child
      onMoveEntry(draggedName, targetEntry.name, getChildren(targetEntry.name).length)
    } else {
      // Insert before or after target at same parent level
      const targetParent = targetEntry.parent ?? null
      const siblings = entries
        .filter(e => (e.parent ?? null) === targetParent && e.name !== draggedName)
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      const targetIdx = siblings.findIndex(e => e.name === targetEntry.name)
      const insertIdx = pos === 'before' ? targetIdx : targetIdx + 1
      onMoveEntry(draggedName, targetParent, Math.max(0, insertIdx))
    }

    setDragging(null)
    setDragOver(null)
    dragCounterRef.current = {}
  }

  // Drop on empty children area → append to that section
  const handleDropOnSection = (e, parentName) => {
    e.preventDefault()
    e.stopPropagation()
    const draggedName = dragging || e.dataTransfer.getData('text/plain')
    if (!draggedName) return
    const draggedEntry = entries.find(en => en.name === draggedName)
    if (!draggedEntry || draggedEntry.entry_type === 'submenu') return // don't move submenus into submenus
    onMoveEntry(draggedName, parentName, getChildren(parentName).length)
    setDragging(null)
    setDragOver(null)
    dragCounterRef.current = {}
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const renderCard = (entry, depth = 0) => {
    const isSubmenu = entry.entry_type === 'submenu'
    const isSelected = entry.name === selectedEntryId
    const isExpanded = expanded.has(entry.name) || !!query
    const isDisabled = !entry.enabled
    const children = isSubmenu ? getChildren(entry.name) : []
    const isDragging = dragging === entry.name
    const dropPos = dragOver?.name === entry.name ? dragOver.pos : null

    const visibleChildren = query
      ? children.filter(c =>
          matchesQuery(c) ||
          (c.entry_type === 'submenu' && getChildren(c.name).some(matchesQuery))
        )
      : children

    if (query && !matchesQuery(entry) && !(isSubmenu && visibleChildren.length > 0)) return null

    return (
      <div
        key={entry.name}
        data-entry-name={entry.name}
        className={[
          'bc-entry',
          isSubmenu ? 'bc-submenu' : 'bc-leaf',
          depth > 0 ? 'bc-nested' : '',
          isSelected ? 'bc-selected' : '',
          isDisabled ? 'bc-disabled' : '',
          isDragging ? 'bc-dragging' : '',
          dropPos === 'before' ? 'bc-drop-before' : '',
          dropPos === 'after' ? 'bc-drop-after' : '',
          dropPos === 'into' ? 'bc-drop-into' : '',
        ].filter(Boolean).join(' ')}
        onDragOver={(e) => handleDragOver(e, entry)}
        onDragEnter={(e) => handleDragEnter(e, entry.name)}
        onDragLeave={(e) => handleDragLeave(e, entry.name)}
        onDrop={(e) => handleDrop(e, entry)}
      >
        <div
          className="bc-card-head"
          draggable
          onDragStart={(e) => handleDragStart(e, entry)}
          onDragEnd={handleDragEnd}
          onClick={isSubmenu ? (e) => toggleExpand(entry.name, e) : () => onSelectEntry(entry.name)}
        >
          <span className="bc-drag-handle" title="Drag to reorder">⠿</span>
          <span className="bc-icon">{entry.icon || (isSubmenu ? '📁' : '⚙')}</span>
          <span className="bc-title">{entry.title || entry.name}</span>
          {!entry.enabled && <span className="bc-badge bc-badge-off">off</span>}
          {isSubmenu && (
            <button
              className="bc-expand-btn"
              onClick={(e) => toggleExpand(entry.name, e)}
              aria-label={isExpanded ? 'Collapse section' : 'Expand section'}
            >
              {isExpanded ? '▾' : '▸'}
            </button>
          )}
        </div>

        {isSubmenu && isExpanded && (
          <div
            className="bc-children"
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
            onDrop={(e) => handleDropOnSection(e, entry.name)}
          >
            <div className="bc-children-grid">
              {visibleChildren.map(child => renderCard(child, depth + 1))}
            </div>
            <button
              className="bc-add-child-btn"
              onClick={() => onOpenWizard(entry.name)}
            >
              + Add entry
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="builder-cards">
      <div className="bc-toolbar">
        <input
          type="search"
          className="bc-search"
          placeholder="Search entries…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <div className="bc-bulk-actions">
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setExpanded(new Set(entries.filter(e => e.entry_type === 'submenu').map(e => e.name)))}
            title="Expand all submenus"
          >
            Expand all
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setExpanded(new Set())}
            title="Collapse all submenus"
          >
            Collapse all
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => onSetEntriesEnabled(entries.map(e => e.name), true)}
          >
            Enable all
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => onSetEntriesEnabled(entries.map(e => e.name), false)}
          >
            Disable all
          </button>
          <button className="btn btn-sm btn-primary" onClick={() => onOpenWizard()}>
            + Add Entry
          </button>
        </div>
      </div>

      <div className="bc-root-list">
        {rootEntries.map(e => renderCard(e, 0))}
        {rootEntries.length === 0 && (
          <div className="bc-empty">
            <p>No menu entries yet.</p>
            <button className="btn btn-primary" onClick={() => onOpenWizard()}>Add first entry</button>
          </div>
        )}
      </div>
    </div>
  )
}
