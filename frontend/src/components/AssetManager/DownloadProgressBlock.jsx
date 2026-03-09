export default function DownloadProgressBlock({
  title,
  progress,
  tone = 'primary',
  unit = 'GB',
  divisor = 1024 * 1024 * 1024,
  decimals = 2,
  showExtraction = false,
  extractingTone = 'success',
}) {
  if (!progress) return null
  const downloaded = ((progress.downloaded || 0) / divisor).toFixed(decimals)
  const total = ((progress.total || 0) / divisor).toFixed(decimals)

  return (
    <div className="dl-progress-block">
      <div className="dl-progress-title">
        {title}
        {showExtraction && progress.status === 'extracting' && (
          <span className={`dl-progress-stage dl-progress-stage-${extractingTone}`}>(Extracting...)</span>
        )}
        {showExtraction && progress.status === 'extracted' && (
          <span className="dl-progress-stage dl-progress-stage-success">
            ✓ Extracted ({progress.file_count || 0} files)
          </span>
        )}
      </div>
      <div className="dl-progress-meta">
        <span>{progress.percentage || 0}%</span>
        <span>{downloaded} {unit} / {total} {unit}</span>
      </div>
      <progress
        className={`dl-progress-meter dl-progress-meter-${tone}`}
        value={progress.percentage || 0}
        max="100"
      />
    </div>
  )
}
