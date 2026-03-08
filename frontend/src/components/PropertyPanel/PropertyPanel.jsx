import { useCallback, useEffect, useMemo, useState } from 'react'
import './PropertyPanel.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

const CMDLINE_BASE_SETS = [
  {
    id: 'base',
    name: 'Base network',
    description: 'Minimal network defaults',
    tokens: ['ip=dhcp'],
  },
  {
    id: 'quiet_ui',
    name: 'Quiet UI',
    description: 'Reduce noise and keep splash',
    tokens: ['quiet', 'splash'],
  },
  {
    id: 'casper_nfs_overlay',
    name: 'Casper NFS overlay',
    description: 'Overlay for casper live boot via NFS',
    tokens: ['boot=casper', 'netboot=nfs', 'ignore_uuid', 'fsck.mode=skip', 'cloud-init=disabled'],
  },
  {
    id: 'casper_iso_overlay',
    name: 'Casper ISO overlay',
    description: 'Overlay for casper live boot with URL',
    tokens: ['boot=casper', 'cloud-init=disabled'],
  },
  {
    id: 'installer_auto_overlay',
    name: 'Installer auto overlay',
    description: 'Auto-install priority defaults',
    tokens: ['auto=true', 'priority=critical'],
  },
]

const CMDLINE_SUGGESTIONS = [
  { token: 'ip=dhcp', hint: 'DHCP network config' },
  { token: 'boot=casper', hint: 'Ubuntu casper live boot' },
  { token: 'netboot=nfs', hint: 'Stream rootfs via NFS' },
  { token: 'nfsroot=SERVER:/path', hint: 'NFS export path' },
  { token: 'url=http://SERVER/ubuntu.iso', hint: 'ISO URL for live boot' },
  { token: 'auto=true', hint: 'Enable unattended install flow' },
  { token: 'priority=critical', hint: 'Installer non-interactive priority' },
  { token: 'cloud-init=disabled', hint: 'Disable cloud-init stage' },
  { token: 'ignore_uuid', hint: 'Ignore media UUID checks' },
  { token: 'fsck.mode=skip', hint: 'Skip filesystem check' },
  { token: 'quiet', hint: 'Reduce boot verbosity' },
  { token: 'splash', hint: 'Enable splash screen' },
]

const tokenizeCmdline = (value) => {
  if (!value?.trim()) return []
  return value.match(/(?:[^\s"]+|"[^"]*")+/g) || []
}

const getTokenKey = (token) => (token.includes('=') ? token.split('=')[0] : token)

function PropertyPanel({ entry, onUpdateEntry, onDeleteEntry, entries }) {
  const [expertMode, setExpertMode] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [preseedProfiles, setPreseedProfiles] = useState([])
  const [customCmdlineSets, setCustomCmdlineSets] = useState(() => {
    try {
      const raw = localStorage.getItem('ipxe_cmdline_custom_sets')
      const parsed = raw ? JSON.parse(raw) : []
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })
  const [selectedCmdlineSet, setSelectedCmdlineSet] = useState('base')
  const [newSetName, setNewSetName] = useState('')
  const [recipeSuggestionState, setRecipeSuggestionState] = useState({ key: '', tokens: [] })

  const cmdlineSetLibrary = useMemo(
    () => [...CMDLINE_BASE_SETS, ...customCmdlineSets],
    [customCmdlineSets]
  )

  useEffect(() => {
    try {
      localStorage.setItem('ipxe_cmdline_custom_sets', JSON.stringify(customCmdlineSets))
    } catch {
      // ignore storage write errors
    }
  }, [customCmdlineSets])

  const detectScenarioFromEntry = useCallback(() => {
    if (entry?.entry_type !== 'boot') return null
    const versionPath = (entry?.kernel || '').split('/')[0]
    if (!versionPath) return null

    if (versionPath.startsWith('ubuntu-')) {
      if (entry?.boot_mode === 'live') return 'ubuntu_live'
      if (entry?.boot_mode === 'preseed') return 'ubuntu_preseed'
      return 'ubuntu_netboot'
    }

    if (versionPath.startsWith('debian-')) {
      if (entry?.boot_mode === 'preseed') return 'debian_preseed'
      if (entry?.boot_mode === 'live') return 'debian_live'
      return 'debian_netboot'
    }

    if (versionPath.startsWith('systemrescue-')) return 'systemrescue'
    if (versionPath.startsWith('kaspersky-')) return 'kaspersky'
    return null
  }, [entry])

  const recipeScenario = detectScenarioFromEntry()
  const recipeVersionPath = (entry?.kernel || '').split('/')[0]
  const recipeKey = recipeScenario && recipeVersionPath
    ? `${recipeScenario}:${recipeVersionPath}:${entry?.preseed_profile || ''}`
    : ''
  const recipeTokenSuggestions = recipeSuggestionState.key === recipeKey ? recipeSuggestionState.tokens : []

  useEffect(() => {
    if (!recipeKey || !recipeScenario || !recipeVersionPath) return

    let cancelled = false
    const params = new URLSearchParams({
      version_path: recipeVersionPath,
      scenario: recipeScenario,
    })
    if (entry?.preseed_profile) {
      params.set('preseed_profile', entry.preseed_profile)
    }

    fetch(`/api/assets/boot-recipe?${params.toString()}`)
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return
        const options = data?.options || []
        const recipe = options.find((opt) => opt.recommended) || options[0]
        const tokens = tokenizeCmdline(recipe?.cmdline || '')
        setRecipeSuggestionState({ key: recipeKey, tokens })
      })
      .catch(() => {
        if (!cancelled) setRecipeSuggestionState({ key: recipeKey, tokens: [] })
      })

    return () => {
      cancelled = true
    }
  }, [entry, recipeKey, recipeScenario, recipeVersionPath])

  const isDebianPreseedEntry = (
    entry?.entry_type === 'boot' &&
    entry?.boot_mode === 'preseed' &&
    (entry?.kernel || '').startsWith('debian-')
  )

  const detectPreseedProfile = useCallback(() => {
    if (entry?.preseed_profile) return entry.preseed_profile
    const match = (entry?.cmdline || '').match(/\/preseed\/([a-zA-Z0-9_-]+)\.cfg/)
    return match?.[1] || ''
  }, [entry])

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
  }, [entry, onUpdateEntry])

  useEffect(() => {
    if (!isDebianPreseedEntry) return

    let cancelled = false

    fetch('/api/boot/preseed/profiles')
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return
        setPreseedProfiles(data.profiles || [])
      })
      .catch(() => {
        if (!cancelled) setPreseedProfiles([])
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

  const mergeTokensIntoCmdline = (incomingTokens) => {
    const currentTokens = tokenizeCmdline(entry.cmdline || '')
    let nextTokens = [...currentTokens]
    incomingTokens.forEach((token) => {
      const key = getTokenKey(token)
      const idx = nextTokens.findIndex((existing) => getTokenKey(existing) === key)
      if (idx >= 0) nextTokens[idx] = token
      else nextTokens.push(token)
    })
    handleFieldChange('cmdline', nextTokens.join(' ').trim())
  }

  const replaceCmdlineWithSet = () => {
    const set = cmdlineSetLibrary.find((item) => item.id === selectedCmdlineSet)
    if (!set) return
    handleFieldChange('cmdline', set.tokens.join(' '))
  }

  const mergeCmdlineSet = () => {
    const set = cmdlineSetLibrary.find((item) => item.id === selectedCmdlineSet)
    if (!set) return
    mergeTokensIntoCmdline(set.tokens)
  }

  const insertTokenSuggestion = (token) => {
    mergeTokensIntoCmdline([token])
  }

  const saveCurrentAsCustomSet = () => {
    const name = newSetName.trim()
    if (!name) return
    const tokens = tokenizeCmdline(entry.cmdline || '')
    if (tokens.length === 0) return
    const id = `custom_${name.toLowerCase().replace(/[^a-z0-9_-]+/g, '_')}_${Date.now()}`
    const set = {
      id,
      name,
      description: 'User custom set',
      tokens,
    }
    setCustomCmdlineSets((prev) => [...prev, set])
    setSelectedCmdlineSet(id)
    setNewSetName('')
  }

  const deleteSelectedCustomSet = () => {
    if (!selectedCmdlineSet.startsWith('custom_')) return
    setCustomCmdlineSets((prev) => prev.filter((set) => set.id !== selectedCmdlineSet))
    setSelectedCmdlineSet('base')
  }

  const cmdlineWarnings = (() => {
    const tokens = tokenizeCmdline(entry.cmdline || '')
    const keys = tokens.map(getTokenKey)
    const warnings = []
    const keyCounts = keys.reduce((acc, key) => ({ ...acc, [key]: (acc[key] || 0) + 1 }), {})

    Object.entries(keyCounts).forEach(([key, count]) => {
      if (count > 1 && key.includes('.')) {
        warnings.push(`Duplicate key "${key}" detected (${count}x).`)
      }
    })

    const has = (prefix) => tokens.some((token) => token === prefix || token.startsWith(`${prefix}=`))
    if (has('netboot') && !has('nfsroot') && tokens.some((token) => token.startsWith('netboot=nfs'))) {
      warnings.push('netboot=nfs usually requires nfsroot=SERVER:/path.')
    }
    if (has('boot') && !tokens.some((token) => token.startsWith('boot=casper')) && has('cloud-init')) {
      warnings.push('cloud-init options are commonly used with boot=casper flows.')
    }
    return warnings
  })()

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
            aria-label="Move entry up"
          >
            ▲
          </button>
          <button
            className="btn-icon"
            onClick={handleMoveDown}
            disabled={!canMoveDown}
            title="Move down"
            aria-label="Move entry down"
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
              <div className="cmdline-builder">
                <div className="cmdline-builder-row">
                  <select
                    className="form-control cmdline-set-select"
                    value={selectedCmdlineSet}
                    onChange={(e) => setSelectedCmdlineSet(e.target.value)}
                  >
                    {cmdlineSetLibrary.map((set) => (
                      <option key={set.id} value={set.id}>{set.name}</option>
                    ))}
                  </select>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={mergeCmdlineSet}>
                    Merge set
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={replaceCmdlineWithSet}>
                    Replace cmdline
                  </button>
                </div>
                <small className="form-hint">
                  {cmdlineSetLibrary.find((set) => set.id === selectedCmdlineSet)?.description}
                </small>
                <div className="cmdline-builder-row">
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Custom set name"
                    value={newSetName}
                    onChange={(e) => setNewSetName(e.target.value)}
                  />
                  <button type="button" className="btn btn-secondary btn-sm" onClick={saveCurrentAsCustomSet}>
                    Save current as set
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={deleteSelectedCustomSet}
                    disabled={!selectedCmdlineSet.startsWith('custom_')}
                  >
                    Delete set
                  </button>
                </div>
                <div className="cmdline-suggestions">
                  {CMDLINE_SUGGESTIONS.map((item) => (
                    <button
                      key={item.token}
                      type="button"
                      className="cmdline-token-chip"
                      onClick={() => insertTokenSuggestion(item.token)}
                      title={item.hint}
                    >
                      {item.token}
                    </button>
                  ))}
                </div>
                {recipeTokenSuggestions.length > 0 && (
                  <>
                    <small className="form-hint">Exact tokens from backend recipe</small>
                    <div className="cmdline-suggestions">
                      {recipeTokenSuggestions.map((token) => (
                        <button
                          key={token}
                          type="button"
                          className="cmdline-token-chip cmdline-token-chip-precise"
                          onClick={() => insertTokenSuggestion(token)}
                          title="Use exact value from backend recipe"
                        >
                          {token}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                {cmdlineWarnings.length > 0 && (
                  <ul className="cmdline-warnings" role="status" aria-live="polite" aria-label="Cmdline warnings">
                    {cmdlineWarnings.map((warning, idx) => <li key={idx}>{warning}</li>)}
                  </ul>
                )}
              </div>
            </div>

            {isDebianPreseedEntry && (
              <div className="form-group">
                <label>Preseed Profile</label>
                <select
                  value={currentPreseedProfile}
                  onChange={(e) => refreshDebianPreseedRecipe(e.target.value)}
                  className="form-control"
                  disabled={preseedProfiles.length === 0}
                >
                  {preseedProfiles.length === 0 && (
                    <option value="">No saved profiles</option>
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
