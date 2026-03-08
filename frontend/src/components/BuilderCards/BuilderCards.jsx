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
}) {
  const [expanded, setExpanded] = useState(() => new Set())
  const [query, setQuery] = useState('')
  const autoExpandedRef = useRef(false)

  // Auto-expand all root submenus once entries are first loaded
  useEffect(() => {
    if (autoExpandedRef.current || entries.length === 0) return
    autoExpandedRef.current = true
    const roots = entries
      .filter(e => !e.parent_name && e.entry_type === 'submenu')
      .map(e => e.name)
    setExpanded(new Set(roots))
  }, [entries])

  // Expand ancestors of selected entry
  useEffect(() => {
    if (!selectedEntryId) return
    setExpanded(prev => {
      const next = new Set(prev)
      let cur = entries.find(e => e.name === selectedEntryId)
      while (cur?.parent_name) {
        next.add(cur.parent_name)
        cur = entries.find(e => e.name === cur.parent_name)
      }
      return next
    })
  }, [selectedEntryId, entries])

  const getChildren = (parentName) =>
    entries
      .filter(e => e.parent_name === parentName)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))

  const rootEntries = useMemo(
    () => entries.filter(e => !e.parent_name).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
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

  const renderCard = (entry, depth = 0) => {
    const isSubmenu = entry.entry_type === 'submenu'
    const isSelected = entry.name === selectedEntryId
    const isExpanded = expanded.has(entry.name) || !!query
    const isDisabled = !entry.enabled
    const children = isSubmenu ? getChildren(entry.name) : []

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
        className={[
          'bc-entry',
          isSubmenu ? 'bc-submenu' : 'bc-leaf',
          depth > 0 ? 'bc-nested' : '',
          isSelected ? 'bc-selected' : '',
          isDisabled ? 'bc-disabled' : '',
        ].filter(Boolean).join(' ')}
      >
        <div className="bc-card-head" onClick={() => onSelectEntry(entry.name)}>
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
          <div className="bc-children">
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
