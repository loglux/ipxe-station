import { useCallback, useEffect, useState } from 'react'
import './PropertyPanel.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

function PropertyPanel({ entry, onUpdateEntry, onDeleteEntry, entries }) {
  const [expertMode, setExpertMode] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [preseedProfiles, setPreseedProfiles] = useState([])
  const [preseedProfilesLoading, setPreseedProfilesLoading] = useState(false)

  const isDebianPreseedEntry = (
    entry?.entry_type === 'boot' &&
    entry?.boot_mode === 'preseed' &&
    (entry?.kernel || '').startsWith('debian-')
  )

  const detectPreseedProfile = useCallback(() => {
    if (entry?.preseed_profile) return entry.preseed_profile
    const match = (entry?.cmdline || '').match(/\/preseed\/([a-zA-Z0-9_-]+)\.cfg/)
    return match?.[1] || ''
  }, [entry?.cmdline, entry?.preseed_profile])

  const currentPreseedProfile = detectPreseedProfile()

  const refreshDebianPreseedRecipe = useCallback(async (profile) => {
    const versionPath = (entry?.kernel || '').split('/')[0]
    if (!versionPath) return

    const params = new URLSearchParams({
      version_path: versionPath,
      scenario: 'debian_preseed',
    })
    if (profile) {
      params.set('preseed_profile', profile)
    }

    try {
      const response = await fetch(`/api/assets/boot-recipe?${params.toString()}`)
      const data = await response.json()
      if (data.error || !data.options?.length) return

      const recipe = data.options.find((option) => option.recommended) || data.options[0]
      onUpdateEntry(entry.name, {
        kernel: recipe.kernel,
        initrd: recipe.initrd,
        cmdline: recipe.cmdline,
        boot_mode: recipe.mode,
        requires_internet: true,
        preseed_profile: profile || null,
      })
    } catch {
      // Keep the panel responsive even if recipe refresh fails.
    }
  }, [entry?.kernel, entry?.name, onUpdateEntry])

  useEffect(() => {
    if (!isDebianPreseedEntry) {
      setPreseedProfiles([])
      return
    }

    let cancelled = false
    setPreseedProfilesLoading(true)

    fetch('/api/boot/preseed/profiles')
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return
        setPreseedProfiles(data.profiles || [])
      })
      .catch(() => {
        if (!cancelled) setPreseedProfiles([])
      })
      .finally(() => {
        if (!cancelled) setPreseedProfilesLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [isDebianPreseedEntry])

  if (!entry) {
    return (
      <div className="property-panel empty">
        <div className="empty-state">
          <div className="empty-icon">📝</div>
          <p>No entry selected</p>
          <p className="text-sm text-muted">
            Select an entry from the menu structure to view and edit its properties
          </p>
        </div>
      </div>
    )
  }

  const handleFieldChange = (field, value) => {
    onUpdateEntry(entry.name, { [field]: value })
  }

  const handleMoveUp = () => {
    const siblings = entries.filter(e => e.parent === entry.parent).sort((a, b) => a.order - b.order)
    const currentIndex = siblings.findIndex(e => e.name === entry.name)

    if (currentIndex > 0) {
      const prevEntry = siblings[currentIndex - 1]
      onUpdateEntry(entry.name, { order: prevEntry.order })
      onUpdateEntry(prevEntry.name, { order: entry.order })
    }
  }

  const handleMoveDown = () => {
    const siblings = entries.filter(e => e.parent === entry.parent).sort((a, b) => a.order - b.order)
    const currentIndex = siblings.findIndex(e => e.name === entry.name)

    if (currentIndex < siblings.length - 1) {
      const nextEntry = siblings[currentIndex + 1]
      onUpdateEntry(entry.name, { order: nextEntry.order })
      onUpdateEntry(nextEntry.name, { order: entry.order })
    }
  }

  // Get available submenus for parent dropdown
  const availableSubmenus = entries
    ? entries.filter(e =>
        e.entry_type === 'submenu' &&
        e.name !== entry.name &&
        e.enabled !== false
      )
    : []

  // Check if can move up/down
  const siblings = entries ? entries.filter(e => e.parent === entry.parent).sort((a, b) => a.order - b.order) : []
  const currentIndex = siblings.findIndex(e => e.name === entry.name)
  const canMoveUp = currentIndex > 0
  const canMoveDown = currentIndex < siblings.length - 1

  return (
    <div className="property-panel">
      <div className="property-header">
        <div>
          <h3>{entry.title || entry.name}</h3>
          <span className="entry-type-badge">{entry.entry_type}</span>
        </div>
        <div className="order-controls">
          <button
            className="btn-icon"
            onClick={handleMoveUp}
            disabled={!canMoveUp}
            title="Move up"
          >
            ▲
          </button>
          <button
            className="btn-icon"
            onClick={handleMoveDown}
            disabled={!canMoveDown}
            title="Move down"
          >
            ▼
          </button>
        </div>
      </div>

      <div className="property-form">
        {/* Basic Fields */}
        <div className="form-group">
          <label>Name *</label>
          <input
            type="text"
            value={entry.name || ''}
            onChange={(e) => handleFieldChange('name', e.target.value)}
            className="form-control"
            placeholder="unique_name"
          />
          <small className="form-hint">Unique identifier (alphanumeric, dash, underscore)</small>
        </div>

        <div className="form-group">
          <label>Title *</label>
          <input
            type="text"
            value={entry.title || ''}
            onChange={(e) => handleFieldChange('title', e.target.value)}
            className="form-control"
            placeholder="Display title"
          />
          <small className="form-hint">Display name shown in menu</small>
        </div>

        {/* Boot entry fields */}
        {entry.entry_type === 'boot' && (
          <>
            <div className="form-group">
              <label>Kernel</label>
              <input
                type="text"
                value={entry.kernel || ''}
                onChange={(e) => handleFieldChange('kernel', e.target.value)}
                className="form-control"
                placeholder="ubuntu-22.04/vmlinuz"
              />
            </div>

            <div className="form-group">
              <label>Initrd</label>
              <input
                type="text"
                value={entry.initrd || ''}
                onChange={(e) => handleFieldChange('initrd', e.target.value)}
                className="form-control"
                placeholder="ubuntu-22.04/initrd"
              />
            </div>

            <div className="form-group">
              <label>Command Line</label>
              <input
                type="text"
                value={entry.cmdline || ''}
                onChange={(e) => handleFieldChange('cmdline', e.target.value)}
                className="form-control"
                placeholder="ip=dhcp ..."
              />
            </div>

            {isDebianPreseedEntry && (
              <div className="form-group">
                <label>Preseed Profile</label>
                <select
                  value={currentPreseedProfile}
                  onChange={(e) => refreshDebianPreseedRecipe(e.target.value)}
                  className="form-control"
                  disabled={preseedProfilesLoading || preseedProfiles.length === 0}
                >
                  {preseedProfiles.length === 0 && (
                    <option value="">
                      {preseedProfilesLoading ? 'Loading profiles...' : 'No saved profiles'}
                    </option>
                  )}
                  {preseedProfiles.map((profile) => (
                    <option key={profile} value={profile}>
                      {profile}
                    </option>
                  ))}
                </select>
                <small className="form-hint">
                  Changing the profile refreshes Debian installer cmdline from the backend recipe.
                </small>
              </div>
            )}
          </>
        )}

        {/* Chain entry fields */}
        {entry.entry_type === 'chain' && (
          <div className="form-group">
            <label>URL *</label>
            <input
              type="text"
              value={entry.url || ''}
              onChange={(e) => handleFieldChange('url', e.target.value)}
              className="form-control"
              placeholder="tftp://server/pxelinux.0"
            />
          </div>
        )}

        {/* Parent submenu — always visible, key for menu organisation */}
        <div className="form-group">
          <label>Parent Submenu</label>
          <select
            value={entry.parent || ''}
            onChange={(e) => handleFieldChange('parent', e.target.value || null)}
            className="form-control"
          >
            <option value="">(root level)</option>
            {availableSubmenus.map(submenu => (
              <option key={submenu.name} value={submenu.name}>
                {submenu.title || submenu.name}
              </option>
            ))}
          </select>
          <small className="form-hint">Move this entry into a submenu</small>
        </div>

        {/* Boot mode — always visible for boot entries */}
        {entry.entry_type === 'boot' && (
          <div className="form-group">
            <label>Boot Mode</label>
            <select
              value={entry.boot_mode || 'rescue'}
              onChange={(e) => handleFieldChange('boot_mode', e.target.value)}
              className="form-control"
            >
              <option value="netboot">Network Boot [NET]</option>
              <option value="live">Live Boot [LIVE]</option>
              <option value="rescue">Rescue / Tool [RESCUE]</option>
              <option value="preseed">Preseed Install</option>
              <option value="custom">Custom (no label)</option>
            </select>
            <small className="form-hint">Controls the label prefix shown in the boot menu</small>
          </div>
        )}

        {/* Description (optional for all) */}
        <div className="form-group">
          <label>Description</label>
          <textarea
            value={entry.description || ''}
            onChange={(e) => handleFieldChange('description', e.target.value)}
            className="form-control"
            rows={2}
            placeholder="Optional description"
          />
        </div>

        {/* Enabled toggle */}
        <div className="form-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={entry.enabled !== false}
              onChange={(e) => handleFieldChange('enabled', e.target.checked)}
            />
            <span>Enabled</span>
          </label>
        </div>

        {/* Expert Mode - low-level fields */}
        {expertMode && (
          <div className="expert-section">
            <div className="expert-header">
              <h4>⚙️ Advanced Settings</h4>
              <span className="badge badge-warning">Expert Mode</span>
            </div>

            <div className="form-group">
              <label>Entry Type</label>
              <select
                value={entry.entry_type || 'boot'}
                onChange={(e) => handleFieldChange('entry_type', e.target.value)}
                className="form-control"
              >
                <option value="boot">Boot Entry</option>
                <option value="submenu">Submenu</option>
                <option value="chain">Chain Load</option>
                <option value="action">Action</option>
                <option value="separator">Separator</option>
              </select>
            </div>

            <div className="form-group">
              <label>Order</label>
              <input
                type="number"
                value={entry.order || 0}
                onChange={(e) => handleFieldChange('order', parseInt(e.target.value) || 0)}
                className="form-control"
                min="0"
              />
              <small className="form-hint">Lower numbers appear first</small>
            </div>

            {entry.entry_type === 'boot' && (
              <>
                <div className="form-group">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={entry.requires_internet || false}
                      onChange={(e) => handleFieldChange('requires_internet', e.target.checked)}
                    />
                    <span>Requires Internet Connection</span>
                  </label>
                </div>
                <div className="form-group">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={entry.requires_iso || false}
                      onChange={(e) => handleFieldChange('requires_iso', e.target.checked)}
                    />
                    <span>Requires ISO File</span>
                  </label>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="property-actions">
        <button
          className={`btn btn-sm ${expertMode ? 'btn-warning' : 'btn-secondary'}`}
          onClick={() => setExpertMode(!expertMode)}
        >
          {expertMode ? '👤 Simple Mode' : '🔧 Expert Mode'}
        </button>
        <button
          className="btn btn-danger btn-sm"
          onClick={() => setDeleteConfirmOpen(true)}
        >
          🗑️ Delete
        </button>
      </div>

      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        title="Delete entry?"
        message={`"${entry.title || entry.name}" will be removed from the menu.`}
        confirmLabel="Delete"
        danger
        onConfirm={() => { setDeleteConfirmOpen(false); onDeleteEntry?.(entry.name) }}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </div>
  )
}

export default PropertyPanel
