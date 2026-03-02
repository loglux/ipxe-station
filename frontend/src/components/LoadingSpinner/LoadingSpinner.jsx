import './LoadingSpinner.css'

function LoadingSpinner({ size = 'md', label = 'Loading…', inline = false }) {
  return (
    <span className={`spinner-wrap ${inline ? 'spinner-inline' : ''}`} aria-label={label}>
      <span className={`spinner spinner-${size}`} aria-hidden="true" />
      {!inline && <span className="spinner-label">{label}</span>}
    </span>
  )
}

export default LoadingSpinner
