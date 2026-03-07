import { useState, useEffect, useCallback } from 'react'
import './AddEntryWizard.css'
import LoadingSpinner from '../LoadingSpinner/LoadingSpinner'
import { CATEGORIES, getScenariosByCategory, getScenario, createEntryFromScenario } from '../../data/scenarios'

// Maps boot mode → short label used in entry title
const MODE_TITLE_LABELS = {
  iso:      'ISO',
  squashfs: 'Squashfs',
  nfs:      'NFS',
  http:     'HTTP',
  netboot:  'Netboot',
}

// Build entry title: strip existing parenthetical from displayName, add mode label
const buildTitle = (displayName, version, mode) => {
  const base = displayName.replace(/\s*\([^)]*\)\s*$/, '').trim()
  const modeLabel = MODE_TITLE_LABELS[mode]
  return modeLabel ? `${base} (${modeLabel}) ${version}` : `${base} ${version}`
}

// Maps scenario ID → catalog key returned by /api/assets/catalog
const SCENARIO_CATALOG_KEY = {
  ubuntu_netboot: 'ubuntu',
  ubuntu_live:    'ubuntu',
  ubuntu_preseed: 'ubuntu',
  debian_netboot: 'debian',
  debian_preseed: 'debian',
  debian_live: 'debian',
  systemrescue:   'rescue',
  kaspersky:      'kaspersky',
}

const RECIPE_SCENARIOS = new Set([
  'ubuntu_netboot',
  'ubuntu_live',
  'ubuntu_preseed',
  'debian_netboot',
  'debian_preseed',
  'debian_live',
  'systemrescue',
  'kaspersky',
])

const MANUAL_ISO_SCENARIOS = new Set(['systemrescue', 'kaspersky', 'hiren'])

const MANUAL_ISO_MATCHERS = {
  systemrescue: (path, category) => {
    const p = path.toLowerCase()
    const c = (category || '').toLowerCase()
    return c === 'rescue' || p.includes('systemrescue') || p.includes('sysres')
  },
  kaspersky: (path, category) => {
    const p = path.toLowerCase()
    const c = (category || '').toLowerCase()
    return c === 'antivirus' || p.includes('kaspersky') || p.includes('krd')
  },
  hiren: (path, category) => {
    const p = path.toLowerCase()
    const c = (category || '').toLowerCase()
    return c === 'tools' || p.includes('hiren') || p.includes('hbcd')
  },
}

const detectManualBootDefaults = (scenarioId, isoPath, httpFilesSet, httpFiles = []) => {
  const normalizeHttpPath = (value = '') => value.replace(/^\/+/, '').replace(/^http\//, '')
  const normalizedIsoPath = normalizeHttpPath(isoPath)
  const parentDir = normalizedIsoPath.includes('/')
    ? normalizedIsoPath.split('/').slice(0, -1).join('/')
    : ''
  const join = (relative) => (parentDir ? `${parentDir}/${relative}` : relative)
  const normalizedSet = new Set(
    Array.from(httpFilesSet || []).map((p) => normalizeHttpPath(String(p))),
  )
  const has = (relative) => normalizedSet.has(normalizeHttpPath(join(relative)))
  const parentPrefix = parentDir ? `${parentDir}/` : ''
  const localFiles = (Array.isArray(httpFiles) ? httpFiles : [])
    .map((p) => normalizeHttpPath(String(p)))
    .filter((p) => (parentPrefix ? p.startsWith(parentPrefix) : true))
    .map((p) => (parentPrefix ? p.slice(parentPrefix.length) : p))

  const findLocalBySuffix = (suffixes = []) => {
    const wanted = suffixes.map((s) => s.toLowerCase())
    for (const item of localFiles) {
      const v = item.toLowerCase()
      if (wanted.some((s) => v === s || v.endsWith(`/${s}`))) {
        return item
      }
    }
    return ''
  }

  if (scenarioId === 'hiren') {
    const localWimboot = has('wimboot') ? 'wimboot' : findLocalBySuffix(['wimboot'])
    const globalWimboot = normalizedSet.has('wimboot') ? 'wimboot' : ''
    const wimbootPath = localWimboot ? join(localWimboot) : (globalWimboot || '')
    const bootmgrLocal = has('bootmgr') ? 'bootmgr' : findLocalBySuffix(['bootmgr'])
    const bcdLocal = has('Boot/BCD')
      ? 'Boot/BCD'
      : has('boot/BCD')
        ? 'boot/BCD'
        : findLocalBySuffix(['Boot/BCD', 'boot/BCD'])
    const sdiLocal = has('Boot/boot.sdi')
      ? 'Boot/boot.sdi'
      : has('boot/boot.sdi')
        ? 'boot/boot.sdi'
        : findLocalBySuffix(['Boot/boot.sdi', 'boot/boot.sdi'])
    const wimLocal = has('sources/boot.wim')
      ? 'sources/boot.wim'
      : has('Sources/boot.wim')
        ? 'Sources/boot.wim'
        : findLocalBySuffix(['sources/boot.wim', 'Sources/boot.wim'])
    const winpeReady = Boolean(wimbootPath && wimLocal)
    const fullBundleReady = Boolean(bootmgrLocal && bcdLocal && sdiLocal)

    if (winpeReady) {
      return {
        kernel: wimbootPath,
        initrd: fullBundleReady ? join(bootmgrLocal) : join(wimLocal),
        cmdline: '',
        autodetected: true,
        severity: 'success',
        hiren_winpe_ready: true,
        hiren_bootmgr: fullBundleReady ? join(bootmgrLocal) : '',
        hiren_bcd: fullBundleReady ? join(bcdLocal) : '',
        hiren_boot_sdi: fullBundleReady ? join(sdiLocal) : '',
        hiren_boot_wim: join(wimLocal),
        hint: fullBundleReady
          ? '✅ Detected Hiren WinPE assets (wimboot + bootmgr/BCD/boot.sdi/boot.wim).'
          : '✅ Detected minimal WinPE assets (wimboot + boot.wim). Full bundle (bootmgr/BCD/boot.sdi) is optional.',
      }
    }

    const hasLinuxFallback = has('vmlinuz') && has('initrd')
    if (hasLinuxFallback) {
      return {
        kernel: join('vmlinuz'),
        initrd: join('initrd'),
        cmdline: 'ip=dhcp',
        autodetected: false,
        severity: 'warning',
        hiren_winpe_ready: false,
        hint: '⚠️ Linux fallback detected (vmlinuz/initrd). Verify this image is not PE-only.',
      }
    }

    return {
      kernel: '',
      initrd: '',
      cmdline: '',
      autodetected: false,
      severity: 'warning',
      hiren_winpe_ready: false,
      hint: 'ℹ️ WinPE bundle not fully detected near ISO. ISO (legacy memdisk, BIOS) can still be used; for WinPE mode keep wimboot + bootmgr + Boot/BCD + Boot/boot.sdi + sources/boot.wim together.',
    }
  }

  return {
    kernel: join('vmlinuz'),
    initrd: join('initrd'),
    cmdline: 'ip=dhcp',
    autodetected: false,
    severity: 'warning',
    hiren_winpe_ready: false,
    hint: `⚠️ Manual asset selected: ${isoPath}. Verify kernel/initrd/cmdline manually.`,
  }
}

const buildHirenManualBootOptions = (version) => {
  const isoPath = version?.iso || ''
  const options = []

  if (version?.autodetected && version?.kernel && version?.initrd) {
    options.push({
      mode: 'winpe',
      label: 'WinPE (auto-detected)',
      kernel: version.kernel,
      initrd: version.initrd,
      cmdline: version.cmdline || '',
      recommended: true,
    })
  }

  if (isoPath) {
    options.push({
      mode: 'iso',
      label: 'ISO (legacy memdisk, BIOS)',
      kernel: 'memdisk',
      initrd: isoPath,
      cmdline: 'iso raw',
      recommended: options.length === 0,
    })
  }

  options.push({
    mode: 'manual',
    label: 'Manual paths',
    kernel: version?.kernel || '',
    initrd: version?.initrd || '',
    cmdline: version?.cmdline || '',
    recommended: options.length === 0,
  })

  return options
}

const buildGenericManualIsoBootOptions = (version) => {
  const isoPath = version?.iso || ''
  const options = []

  if (isoPath) {
    options.push({
      mode: 'iso',
      label: 'ISO (legacy memdisk, BIOS)',
      kernel: 'memdisk',
      initrd: isoPath,
      cmdline: 'iso raw',
      recommended: true,
    })
  }

  options.push({
    mode: 'manual',
    label: 'Manual paths',
    kernel: version?.kernel || '',
    initrd: version?.initrd || '',
    cmdline: version?.cmdline || '',
    recommended: options.length === 0,
  })

  return options
}

function AddEntryWizard({ isOpen, onClose, onAddEntry, entries = [], initialCategory = null }) {
  const [step, setStep] = useState(1)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [selectedScenario, setSelectedScenario] = useState(null)
  const [entryName, setEntryName] = useState('')
  const [entryTitle, setEntryTitle] = useState('')
  const [parentSubmenu, setParentSubmenu] = useState(null)
  const [availableVersions, setAvailableVersions] = useState([])
  const [selectedVersion, setSelectedVersion] = useState(null)
  const [kernel, setKernel] = useState('')
  const [initrd, setInitrd] = useState('')
  const [cmdline, setCmdline] = useState('')
  const [bootOptions, setBootOptions] = useState([])
  const [selectedBootOption, setSelectedBootOption] = useState(null)
  const [recipeLoading, setRecipeLoading] = useState(false)
  const [recipeError, setRecipeError] = useState(null)
  const [preseedProfiles, setPreseedProfiles] = useState([])
  const [selectedPreseedProfile, setSelectedPreseedProfile] = useState('')
  const [createError, setCreateError] = useState(null)
  const [manualAssetsHint, setManualAssetsHint] = useState('')
  const [manualAssetsHintKind, setManualAssetsHintKind] = useState('info')

  // Handle initial category selection
  useEffect(() => {
    if (isOpen && initialCategory) {
      const timerId = setTimeout(() => {
        setSelectedCategory(initialCategory)
        setStep(2)
      }, 0)
      return () => clearTimeout(timerId)
    }
  }, [isOpen, initialCategory])

  const handleVersionSelect = useCallback(async (version, profileOverride = null) => {
    setSelectedVersion(version)
    setKernel(version.kernel || '')
    setInitrd(version.initrd || '')
    setCmdline(version.manual ? (version.cmdline || 'ip=dhcp') : '')
    setBootOptions([])
    setSelectedBootOption(null)
    setRecipeError(null)
    setManualAssetsHint('')
    setManualAssetsHintKind('info')

    // Update title to include version (mode refined after recipe loads)
    const scenario = getScenario(selectedScenario)
    setEntryTitle(`${scenario.displayName} ${version.version_label || version.version}`)

    if (version.manual) {
      const manualOptions = selectedScenario === 'hiren'
        ? buildHirenManualBootOptions(version)
        : buildGenericManualIsoBootOptions(version)
      setBootOptions(manualOptions)
      const preferred = manualOptions.find((opt) => opt.recommended) || manualOptions[0]
      setSelectedBootOption(preferred || null)
      if (preferred) {
        setKernel(preferred.kernel || '')
        setInitrd(preferred.initrd || '')
        setCmdline(preferred.cmdline || '')
        setEntryTitle(buildTitle(scenario.displayName, version.version, preferred.mode))
      }
      setManualAssetsHint(version.manual_hint || '')
      setManualAssetsHintKind(version.manual_hint_kind || (version.autodetected ? 'success' : 'warning'))
      return
    }

    if (!RECIPE_SCENARIOS.has(selectedScenario)) {
      return
    }

    // Fetch boot recipe from backend
    const catalogKey = SCENARIO_CATALOG_KEY[selectedScenario] || selectedScenario
    const versionPath = `${catalogKey}-${version.version}`
    const preseedProfile = profileOverride ?? selectedPreseedProfile
    setRecipeLoading(true)
    try {
      const params = new URLSearchParams({
        version_path: versionPath,
        scenario: selectedScenario,
      })
      if (selectedScenario === 'debian_preseed' && preseedProfile) {
        params.set('preseed_profile', preseedProfile)
      }
      const resp = await fetch(`/api/assets/boot-recipe?${params.toString()}`)
      const data = await resp.json()
      if (data.error) {
        setRecipeError(data.error)
      } else if (data.options?.length > 0) {
        setBootOptions(data.options)
        const rec = data.options.find(o => o.recommended) || data.options[0]
        setSelectedBootOption(rec)
        setKernel(rec.kernel)
        setInitrd(rec.initrd)
        setCmdline(rec.cmdline)
        setEntryTitle(buildTitle(scenario.displayName, version.version, rec.mode))
      }
    } catch {
      setRecipeError('Failed to load boot recipe')
    } finally {
      setRecipeLoading(false)
    }
  }, [selectedPreseedProfile, selectedScenario])

  const fetchAvailableAssets = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/catalog')
      const catalog = await response.json()
      let assets = { http: [], asset_labels: {} }
      if (
        selectedScenario === 'systemrescue' ||
        selectedScenario === 'kaspersky' ||
        selectedScenario === 'hiren'
      ) {
        const assetsResp = await fetch('/api/assets')
        assets = await assetsResp.json()
      }

      const scenario = getScenario(selectedScenario)
      if (!scenario || !scenario.assetDiscovery) {
        setAvailableVersions([])
        return
      }

      const catalogKey = SCENARIO_CATALOG_KEY[selectedScenario]
      let versions = catalogKey ? (catalog[catalogKey] || []) : []

      // Filter to only versions that have at least kernel+initrd or squashfs/iso to boot from
      const validVersions = versions.filter(v => (v.kernel && v.initrd) || v.squashfs || v.iso)
      const labels = assets?.asset_labels && typeof assets.asset_labels === 'object'
        ? assets.asset_labels
        : {}
      const httpFiles = Array.isArray(assets?.http) ? assets.http : []
      const manualIsoVersions = MANUAL_ISO_SCENARIOS.has(selectedScenario)
        ? httpFiles
          .filter((path) => path.toLowerCase().endsWith('.iso'))
          .map((path) => path.replace(/^\/+/, ''))
          .map((path) => {
            const category = labels[path]
              || (path.startsWith('tools/') ? 'tools' : '')
              || (path.startsWith('rescue/') ? 'rescue' : '')
              || (path.startsWith('antivirus/') ? 'antivirus' : '')
              || (path.startsWith('hiren-') ? 'tools' : '')
              || (path.startsWith('hiren/') ? 'tools' : '')
            return { path, category }
          })
          .map((path) => {
            return {
              path: path.path,
              category: path.category,
              include: MANUAL_ISO_MATCHERS[selectedScenario]?.(path.path, path.category) || false,
            }
          })
          .filter((row) => row.include)
          .map(({ path, category }) => {
            const httpFilesSet = new Set(httpFiles.map((item) => item.replace(/^\/+/, '')))
            const defaults = detectManualBootDefaults(selectedScenario, path, httpFilesSet, httpFiles)
            const parts = path.split('/')
            const fileName = parts.at(-1) || path
            const baseName = fileName.replace(/\.iso$/i, '')
            const parentDir = parts.length > 1 ? parts.slice(0, -1).join('/') : ''
            const categoryLabel = category || 'uncategorized'
            return {
              version: `manual:${path}`,
              version_label: `${baseName} (manual ISO, ${categoryLabel})`,
              kernel: defaults.kernel,
              initrd: defaults.initrd,
              iso: path,
              cmdline: defaults.cmdline,
              manual: true,
              autodetected: defaults.autodetected,
              manual_hint: defaults.hint,
              manual_hint_kind: defaults.severity || 'warning',
              hiren_winpe_ready: defaults.hiren_winpe_ready || false,
              hiren_bootmgr: defaults.hiren_bootmgr,
              hiren_bcd: defaults.hiren_bcd,
              hiren_boot_sdi: defaults.hiren_boot_sdi,
              hiren_boot_wim: defaults.hiren_boot_wim,
            }
          })
        : []

      const merged = [...validVersions, ...manualIsoVersions]
      setAvailableVersions(merged)

      // Auto-select if only one version available
      if (merged.length === 1) {
        handleVersionSelect(merged[0])
      }
    } catch (error) {
      console.error('Failed to fetch assets:', error)
      setAvailableVersions([])
      setManualAssetsHint('')
    }
  }, [handleVersionSelect, selectedScenario])

  const fetchPreseedProfiles = useCallback(async () => {
    if (selectedScenario !== 'debian_preseed') {
      setPreseedProfiles([])
      setSelectedPreseedProfile('')
      return
    }

    try {
      const response = await fetch('/api/boot/preseed/profiles')
      const data = await response.json()
      const profiles = data.profiles || []
      const active = data.active_profile || profiles[0] || ''
      setPreseedProfiles(profiles)
      setSelectedPreseedProfile((current) => (
        current && profiles.includes(current) ? current : active
      ))
    } catch {
      setPreseedProfiles([])
      setSelectedPreseedProfile('')
    }
  }, [selectedScenario])

  // Fetch available assets when scenario is selected
  useEffect(() => {
    if (selectedScenario) {
      const timerId = setTimeout(() => {
        fetchAvailableAssets()
        fetchPreseedProfiles()
      }, 0)
      return () => clearTimeout(timerId)
    }
  }, [fetchAvailableAssets, fetchPreseedProfiles, selectedScenario])

  useEffect(() => {
    if (selectedScenario === 'debian_preseed' && selectedVersion && selectedPreseedProfile) {
      handleVersionSelect(selectedVersion, selectedPreseedProfile)
    }
  }, [handleVersionSelect, selectedPreseedProfile, selectedScenario, selectedVersion])

  if (!isOpen) return null

  const handleCategorySelect = (categoryKey) => {
    setSelectedCategory(categoryKey)
    setStep(2)
  }

  const handleScenarioSelect = (scenarioId) => {
    setSelectedScenario(scenarioId)
    const scenario = getScenario(scenarioId)

    // Auto-generate deterministic name and title
    const existingCount = entries.filter((entry) => entry.name.startsWith(`${scenarioId}_`)).length + 1
    setEntryName(`${scenarioId}_${existingCount}`)
    setEntryTitle(scenario.displayName)

    setStep(3)
  }

  const handleCreate = () => {
    if (!selectedScenario || !entryName || !entryTitle) {
      setCreateError('Please fill in all required fields.')
      return
    }
    const scenario = getScenario(selectedScenario)
    const required = scenario?.fields?.required || []

    const requiredValues = {
      name: entryName,
      title: entryTitle,
      kernel,
      initrd,
      cmdline,
    }

    if (selectedBootOption?.mode === 'manual' && (!kernel || kernel.trim() === '')) {
      setCreateError('For "Manual paths", field "kernel" is required. Fill kernel path or switch Boot Mode to ISO.')
      return
    }

    for (const field of required) {
      const value = requiredValues[field]
      if (typeof value === 'string' && value.trim() === '') {
        setCreateError(`Field "${field}" is required.`)
        return
      }
      if (value == null) {
        setCreateError(`Field "${field}" is required.`)
        return
      }
    }
    setCreateError(null)

    const requiresIso = selectedBootOption
      ? selectedBootOption.mode === 'iso'
      : undefined
    const hirenWinpeOverrides = selectedScenario === 'hiren' && selectedBootOption?.mode === 'winpe'
      ? {
          hiren_winpe_ready: Boolean(selectedVersion?.hiren_winpe_ready),
          hiren_bootmgr: selectedVersion?.hiren_bootmgr || undefined,
          hiren_bcd: selectedVersion?.hiren_bcd || undefined,
          hiren_boot_sdi: selectedVersion?.hiren_boot_sdi || undefined,
          hiren_boot_wim: selectedVersion?.hiren_boot_wim || undefined,
        }
      : {}

    // Create entry from scenario with auto-populated fields
    const entry = createEntryFromScenario(selectedScenario, {
      name: entryName,
      title: entryTitle,
      parent: parentSubmenu,
      kernel: kernel || undefined,
      initrd: initrd || undefined,
      cmdline: cmdline || undefined,
      requires_iso: requiresIso,
      preseed_profile: selectedScenario === 'debian_preseed' ? (selectedPreseedProfile || undefined) : undefined,
      ...hirenWinpeOverrides,
    })

    onAddEntry(entry)
    handleClose()
  }

  const handleClose = () => {
    setStep(1)
    setSelectedCategory(null)
    setSelectedScenario(null)
    setEntryName('')
    setEntryTitle('')
    setParentSubmenu(null)
    setAvailableVersions([])
    setSelectedVersion(null)
    setKernel('')
    setInitrd('')
    setCmdline('')
    setBootOptions([])
    setSelectedBootOption(null)
    setRecipeLoading(false)
    setRecipeError(null)
    setManualAssetsHint('')
    setManualAssetsHintKind('info')
    setPreseedProfiles([])
    setSelectedPreseedProfile('')
    setCreateError(null)
    onClose()
  }

  const renderStepIndicator = () => {
    return (
      <div className="wizard-steps">
        <div className={`wizard-step ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}>
          <span className="step-number">1</span>
          <span className="step-label">Category</span>
        </div>
        <div className="wizard-step-separator"></div>
        <div className={`wizard-step ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}>
          <span className="step-number">2</span>
          <span className="step-label">Scenario</span>
        </div>
        <div className="wizard-step-separator"></div>
        <div className={`wizard-step ${step >= 3 ? 'active' : ''}`}>
          <span className="step-number">3</span>
          <span className="step-label">Details</span>
        </div>
      </div>
    )
  }

  const renderStep1 = () => {
    return (
      <div className="wizard-step-content">
        <h3>What do you want to add?</h3>
        <p className="step-description">Select a category to see available scenarios</p>

        <div className="category-grid">
          {Object.entries(CATEGORIES).map(([key, category]) => (
            <div
              key={key}
              className="category-card"
              style={{ borderColor: category.color }}
              onClick={() => handleCategorySelect(key)}
            >
              <div className="category-icon">{category.icon}</div>
              <div className="category-name">{category.name}</div>
              <div className="category-description">{category.description}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const renderStep2 = () => {
    const scenarios = getScenariosByCategory(selectedCategory)
    const category = CATEGORIES[selectedCategory]

    return (
      <div className="wizard-step-content">
        <div className="step-header">
          <button className="btn-back" onClick={() => setStep(1)}>
            ← Back
          </button>
          <div>
            <h3>{category.icon} {category.name}</h3>
            <p className="step-description">Choose a specific scenario</p>
          </div>
        </div>

        <div className="scenario-list">
          {scenarios.map((scenario) => (
            <div
              key={scenario.id}
              className="scenario-card"
              onClick={() => handleScenarioSelect(scenario.id)}
            >
              <div className="scenario-header">
                <span className="scenario-icon">{scenario.icon}</span>
                <span className="scenario-name">{scenario.displayName}</span>
              </div>
              <p className="scenario-description">{scenario.description}</p>

              {/* Requirements badges */}
              <div className="scenario-requirements">
                {scenario.generated.requires_internet && (
                  <span className="requirement-badge">🌐 Internet</span>
                )}
                {scenario.generated.requires_iso && (
                  <span className="requirement-badge">💿 ISO</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const renderStep3 = () => {
    const scenario = getScenario(selectedScenario)

    return (
      <div className="wizard-step-content">
        <div className="step-header">
          <button className="btn-back" onClick={() => setStep(2)}>
            ← Back
          </button>
          <div>
            <h3>{scenario.icon} {scenario.displayName}</h3>
            <p className="step-description">Configure entry details</p>
          </div>
        </div>

        <div className="wizard-form">
          {/* Version selector if available assets found */}
          {availableVersions.length > 0 && (
            <div className="form-group">
              <label>Available Version *</label>
              <select
                value={selectedVersion?.version || ''}
                onChange={(e) => {
                  const version = availableVersions.find(v => v.version === e.target.value)
                  if (version) handleVersionSelect(version)
                }}
                className="form-control"
              >
                <option value="">Select a version...</option>
                {availableVersions.map(v => (
                  <option key={v.version} value={v.version}>
                    {scenario.displayName} {v.version_label || v.version}
                  </option>
                ))}
              </select>
              <small className="form-hint">
                ✅ Found {availableVersions.length} downloaded version{availableVersions.length > 1 ? 's' : ''}
              </small>
            </div>
          )}
          {manualAssetsHint && (
            <p className={`form-hint ${manualAssetsHintKind === 'success' ? 'form-hint-success' : manualAssetsHintKind === 'error' ? 'form-hint-error' : ''}`}>
              {manualAssetsHint}
            </p>
          )}

          {/* Boot mode selector — shown once recipe loads */}
          {recipeLoading && <LoadingSpinner size="sm" label="Loading boot options…" inline />}
          {recipeError && <p className="form-hint form-hint-error">{recipeError}</p>}
          {bootOptions.length > 0 && (
            <div className="form-group">
              <label>Boot Mode</label>
              <div className="boot-option-list">
                {bootOptions.map(opt => (
                  <label
                    key={opt.mode}
                    className={`boot-option-item ${selectedBootOption?.mode === opt.mode ? 'selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="bootMode"
                      checked={selectedBootOption?.mode === opt.mode}
                      onChange={() => {
                        setSelectedBootOption(opt)
                        setKernel(opt.kernel)
                        setInitrd(opt.initrd)
                        setCmdline(opt.cmdline)
                        const sc = getScenario(selectedScenario)
                        if (selectedVersion) {
                          setEntryTitle(buildTitle(sc.displayName, selectedVersion.version, opt.mode))
                        }
                      }}
                    />
                    <span>{opt.label}</span>
                    {opt.recommended && <span className="badge-recommended">Recommended</span>}
                  </label>
                ))}
              </div>
              {/* Hint: NFS available but nfs_root not configured */}
              {['ubuntu_live', 'ubuntu_netboot', 'ubuntu_preseed'].includes(selectedScenario) &&
                !bootOptions.some(o => o.mode === 'nfs') && (
                <p className="form-hint" style={{ marginTop: '6px' }}>
                  NFS boot not shown — configure <strong>NFS Root Path</strong> in
                  {' '}<strong>Settings</strong> to enable it (recommended for Server ISOs).
                </p>
              )}
            </div>
          )}

          {selectedScenario === 'debian_preseed' && preseedProfiles.length > 0 && (
            <div className="form-group">
              <label>Preseed Profile</label>
              <select
                value={selectedPreseedProfile}
                onChange={(e) => setSelectedPreseedProfile(e.target.value)}
                className="form-control"
              >
                {preseedProfiles.map((profile) => (
                  <option key={profile} value={profile}>
                    {profile}
                  </option>
                ))}
              </select>
              <small className="form-hint">
                Backend will point this entry to <code>/preseed/{selectedPreseedProfile || 'PROFILE'}.cfg</code>
              </small>
            </div>
          )}

          <div className="form-group">
            <label>Name *</label>
            <input
              type="text"
              value={entryName}
              onChange={(e) => setEntryName(e.target.value)}
              className="form-control"
              placeholder="unique_name"
            />
            <small className="form-hint">
              Unique identifier (alphanumeric, dash, underscore only)
            </small>
          </div>

          <div className="form-group">
            <label>Title *</label>
            <input
              type="text"
              value={entryTitle}
              onChange={(e) => setEntryTitle(e.target.value)}
              className="form-control"
              placeholder="Display title"
            />
            <small className="form-hint">
              Display name shown in the boot menu
            </small>
          </div>

          {/* Show kernel/initrd fields */}
          {scenario.fields.required.includes('kernel') && (
            <div className="form-group">
              <label>Kernel {selectedVersion ? '✅' : '*'}</label>
              <input
                type="text"
                value={kernel}
                onChange={(e) => setKernel(e.target.value)}
                className="form-control"
                placeholder="ubuntu-22.04/vmlinuz"
                readOnly={!!selectedVersion && !selectedVersion.manual}
              />
              <small className="form-hint">
                {selectedVersion ? 'Auto-populated from selected version' : 'Path to kernel file'}
              </small>
            </div>
          )}

          {scenario.fields.required.includes('initrd') && (
            <div className="form-group">
              <label>Initrd {selectedVersion ? '✅' : '*'}</label>
              <input
                type="text"
                value={initrd}
                onChange={(e) => setInitrd(e.target.value)}
                className="form-control"
                placeholder="ubuntu-22.04/initrd"
                readOnly={!!selectedVersion && !selectedVersion.manual}
              />
              <small className="form-hint">
                {selectedVersion ? 'Auto-populated from selected version' : 'Path to initrd file'}
              </small>
            </div>
          )}

          {/* Cmdline — auto-filled by recipe, user can override */}
          {!scenario.fields.forbidden?.includes('cmdline') && (
            <div className="form-group">
              <label>Kernel parameters {selectedBootOption ? '✅' : ''}</label>
              <input
                type="text"
                value={cmdline}
                onChange={(e) => setCmdline(e.target.value)}
                className="form-control"
                placeholder="ip=dhcp boot=casper fetch=..."
              />
              {selectedBootOption ? (
                <small className="form-hint">Auto-generated — you can edit if needed</small>
              ) : (
                <small className="form-hint">Optional kernel command-line parameters</small>
              )}
            </div>
          )}

          <div className="form-group">
            <label>Parent Submenu</label>
            <select
              value={parentSubmenu || ''}
              onChange={(e) => setParentSubmenu(e.target.value || null)}
              className="form-control"
            >
              <option value="">(root level)</option>
              {entries
                .filter(e => e.entry_type === 'submenu' && e.enabled !== false)
                .sort((a, b) => (a.title || a.name).localeCompare(b.title || b.name))
                .map(submenu => (
                  <option key={submenu.name} value={submenu.name}>
                    {submenu.title || submenu.name}
                  </option>
                ))}
            </select>
            <small className="form-hint">
              Optional: place this entry inside a submenu
            </small>
          </div>

          {/* Show help text if available */}
          {scenario.help && (
            <div className="scenario-help">
              <div className="help-header">ℹ️ About this scenario</div>
              <div className="help-content">{scenario.help}</div>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="wizard-overlay" onClick={handleClose}>
      <div className="wizard-modal" onClick={(e) => e.stopPropagation()}>
        <div className="wizard-header">
          <h2>Add New Entry</h2>
          <button className="btn-close" onClick={handleClose}>✕</button>
        </div>

        {renderStepIndicator()}

        <div className="wizard-body">
          {step === 1 && renderStep1()}
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
        </div>

        <div className="wizard-footer">
          <button className="btn btn-secondary" onClick={handleClose}>
            Cancel
          </button>
          {step === 3 && (
            <>
              {createError && <p className="form-hint form-hint-error">{createError}</p>}
              <button className="btn btn-primary" onClick={handleCreate}>
                Create Entry
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default AddEntryWizard
