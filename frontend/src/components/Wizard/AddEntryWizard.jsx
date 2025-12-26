import { useState } from 'react'
import './AddEntryWizard.css'
import { CATEGORIES, getScenariosByCategory, getScenario, createEntryFromScenario } from '../../data/scenarios'

function AddEntryWizard({ isOpen, onClose, onAddEntry }) {
  const [step, setStep] = useState(1)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [selectedScenario, setSelectedScenario] = useState(null)
  const [entryName, setEntryName] = useState('')
  const [entryTitle, setEntryTitle] = useState('')
  const [parentSubmenu, setParentSubmenu] = useState(null)

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

    // Create entry from scenario
    const entry = createEntryFromScenario(selectedScenario, {
      name: entryName,
      title: entryTitle,
      parent: parentSubmenu,
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

          <div className="form-group">
            <label>Parent Submenu</label>
            <select
              value={parentSubmenu || ''}
              onChange={(e) => setParentSubmenu(e.target.value || null)}
              className="form-control"
            >
              <option value="">(root level)</option>
              {/* TODO: populate with actual submenus */}
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
