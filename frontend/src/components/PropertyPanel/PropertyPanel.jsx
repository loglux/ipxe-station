import { useState } from 'react'
import './PropertyPanel.css'

function PropertyPanel({ entry, onUpdateEntry, entries }) {
  const [expertMode, setExpertMode] = useState(false)

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

  // Get available submenus for parent dropdown
  const availableSubmenus = entries
    ? entries.filter(e =>
        e.entry_type === 'submenu' &&
        e.name !== entry.name &&
        e.enabled !== false
      )
    : []

  return (
    <div className="property-panel">
      <div className="property-header">
        <h3>{entry.title || entry.name}</h3>
        <span className="entry-type-badge">{entry.entry_type}</span>
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

        {/* Requirements (for boot entries) */}
        {!expertMode && entry.entry_type === 'boot' && (
          <div className="property-section">
            <h4>Requirements</h4>
            <div className="requirement-badges">
              {entry.requires_internet && <span className="badge badge-info">🌐 Internet</span>}
              {entry.requires_iso && <span className="badge badge-info">💿 ISO File</span>}
              {!entry.requires_internet && !entry.requires_iso && (
                <span className="text-muted text-sm">No special requirements</span>
              )}
            </div>
          </div>
        )}

        {/* Expert Mode - Technical Fields */}
        {expertMode && (
          <div className="expert-section">
            <div className="expert-header">
              <h4>⚙️ Advanced Settings</h4>
              <span className="badge badge-warning">Expert Mode</span>
            </div>

            <div className="form-group">
              <label>Entry Type *</label>
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
              <small className="form-hint">Type of menu entry</small>
            </div>

            {entry.entry_type === 'boot' && (
              <div className="form-group">
                <label>Boot Mode</label>
                <select
                  value={entry.boot_mode || 'netboot'}
                  onChange={(e) => handleFieldChange('boot_mode', e.target.value)}
                  className="form-control"
                >
                  <option value="netboot">Network Boot</option>
                  <option value="live">Live Boot</option>
                  <option value="rescue">Rescue Mode</option>
                  <option value="preseed">Preseed Install</option>
                  <option value="tool">System Tool</option>
                  <option value="custom">Custom</option>
                </select>
                <small className="form-hint">Boot method for this entry</small>
              </div>
            )}

            <div className="form-group">
              <label>Parent Menu</label>
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
              <small className="form-hint">Place this entry inside a submenu</small>
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
              <small className="form-hint">Display order in menu (lower numbers first)</small>
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
        <button className="btn btn-danger btn-sm">🗑️ Delete</button>
      </div>
    </div>
  )
}

export default PropertyPanel
