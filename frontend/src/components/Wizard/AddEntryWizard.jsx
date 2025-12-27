import { useState, useEffect } from 'react'
import './AddEntryWizard.css'
import { CATEGORIES, getScenariosByCategory, getScenario, createEntryFromScenario } from '../../data/scenarios'

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

  // Handle initial category selection
  useEffect(() => {
    if (isOpen && initialCategory) {
      setSelectedCategory(initialCategory)
      setStep(2)
    }
  }, [isOpen, initialCategory])

  // Fetch available assets when scenario is selected
  useEffect(() => {
    if (selectedScenario) {
      fetchAvailableAssets()
    }
  }, [selectedScenario])

  const fetchAvailableAssets = async () => {
    try {
      const response = await fetch('/api/assets/catalog')
      const catalog = await response.json()

      const scenario = getScenario(selectedScenario)
      if (!scenario || !scenario.assetDiscovery) {
        setAvailableVersions([])
        return
      }

      // Determine which catalog to check based on scenario
      let versions = []
      if (selectedScenario.includes('ubuntu')) {
        versions = catalog.ubuntu || []
      } else if (selectedScenario.includes('debian')) {
        versions = catalog.debian || []
      } else if (selectedScenario.includes('systemrescue')) {
        versions = catalog.rescue || []
      } else if (selectedScenario.includes('kaspersky')) {
        // Kaspersky has its own catalog entry
        versions = catalog.kaspersky || []
      }

      // Filter to only versions that have required files
      const validVersions = versions.filter(v => v.kernel && v.initrd)
      setAvailableVersions(validVersions)

      // Auto-select if only one version available
      if (validVersions.length === 1) {
        handleVersionSelect(validVersions[0])
      }
    } catch (error) {
      console.error('Failed to fetch assets:', error)
      setAvailableVersions([])
    }
  }

  const handleVersionSelect = (version) => {
    setSelectedVersion(version)
    setKernel(version.kernel || '')
    setInitrd(version.initrd || '')

    // Update title to include version
    const scenario = getScenario(selectedScenario)
    setEntryTitle(`${scenario.displayName} ${version.version}`)
  }

  if (!isOpen) return null

  const handleCategorySelect = (categoryKey) => {
    setSelectedCategory(categoryKey)
    setStep(2)
  }

  const handleScenarioSelect = (scenarioId) => {
    setSelectedScenario(scenarioId)
    const scenario = getScenario(scenarioId)

    // Auto-generate name and title
    const timestamp = Date.now().toString().slice(-4)
    setEntryName(`${scenarioId}_${timestamp}`)
    setEntryTitle(scenario.displayName)

    setStep(3)
  }

  const handleCreate = () => {
    if (!selectedScenario || !entryName || !entryTitle) {
      alert('Please fill in all required fields')
      return
    }

    // Create entry from scenario with auto-populated fields
    const entry = createEntryFromScenario(selectedScenario, {
      name: entryName,
      title: entryTitle,
      parent: parentSubmenu,
      kernel: kernel || undefined,
      initrd: initrd || undefined,
      cmdline: cmdline || undefined,
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
                    {scenario.displayName} {v.version}
                  </option>
                ))}
              </select>
              <small className="form-hint">
                ✅ Found {availableVersions.length} downloaded version{availableVersions.length > 1 ? 's' : ''}
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
                readOnly={!!selectedVersion}
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
                readOnly={!!selectedVersion}
              />
              <small className="form-hint">
                {selectedVersion ? 'Auto-populated from selected version' : 'Path to initrd file'}
              </small>
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
            <button className="btn btn-primary" onClick={handleCreate}>
              Create Entry
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default AddEntryWizard
