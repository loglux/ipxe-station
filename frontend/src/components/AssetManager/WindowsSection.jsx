import { useState, useEffect, useCallback } from 'react'
import DownloadProgressBlock from './DownloadProgressBlock'

const WIMBOOT_URL = 'https://github.com/ipxe/wimboot/releases/latest/download/wimboot'
const WIMBOOT_DEST = 'wimboot'

export default function WindowsSection({ downloading, downloadProgress, downloadStatus, onDownload }) {
  const [wimbootStatus, setWimbootStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/assets/wimboot-status')
      const data = await r.json()
      setWimbootStatus(data)
    } catch {
      setWimbootStatus(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchStatus() }, [fetchStatus])

  // Refresh after download completes
  useEffect(() => {
    if (!downloading['wimboot']) return
    const prev = downloading['wimboot']
    return () => { if (prev) fetchStatus() }
  }, [downloading, fetchStatus])

  const winpeFiles = wimbootStatus?.winpe_files || {}
  const winpeReady = winpeFiles.BCD && winpeFiles.boot_sdi && winpeFiles.boot_wim

  const progressKey = WIMBOOT_DEST
  const isDownloading = !!downloading['wimboot']

  return (
    <section className="asset-section">
      <h3>🪟 Windows PE (wimboot)</h3>

      {/* wimboot binary */}
      <div className="download-subsection">
        <h4>wimboot binary</h4>
        <p className="text-sm text-muted download-section-note">
          iPXE bootloader for Windows PE — required for all WinPE boot entries.
          Downloaded from <a href="https://github.com/ipxe/wimboot" target="_blank" rel="noopener noreferrer">ipxe/wimboot</a>.
        </p>

        <div className="distro-item">
          <div className="distro-info">
            {loading ? (
              <span className="text-muted text-sm">Checking…</span>
            ) : wimbootStatus?.wimboot_present ? (
              <div className="distro-name">
                ✅ wimboot present
                <span className="file-badge">{((wimbootStatus.wimboot_size || 0) / 1024).toFixed(0)} KB</span>
              </div>
            ) : (
              <div className="distro-name">⚠️ wimboot not found — download to enable WinPE boot</div>
            )}
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={fetchStatus}
            title="Refresh status"
          >↻</button>
        </div>

        {isDownloading && downloadProgress[progressKey] && (
          <DownloadProgressBlock
            title="wimboot"
            progress={downloadProgress[progressKey]}
            tone="primary"
            unit="KB"
            divisor={1024}
            decimals={0}
          />
        )}
        {downloadStatus['wimboot'] && (
          <div className="download-status">{downloadStatus['wimboot']}</div>
        )}

        <button
          className="btn btn-primary btn-sm"
          style={{ marginTop: 8 }}
          onClick={() => onDownload({ url: WIMBOOT_URL, dest: WIMBOOT_DEST, key: 'wimboot' })}
          disabled={isDownloading}
        >
          {isDownloading ? '⏳ Downloading…' : wimbootStatus?.wimboot_present ? '↻ Re-download wimboot' : '⬇️ Download wimboot'}
        </button>
      </div>

      {/* WinPE files */}
      <div className="download-subsection">
        <h4>WinPE files</h4>
        <p className="text-sm text-muted download-section-note">
          Obtain from <strong>Windows ADK + WinPE add-on</strong> (free from Microsoft, requires Windows to install),
          then upload to <code>/srv/http/winpe/</code> using the <strong>Upload File</strong> button above.
        </p>

        <div className="distro-item">
          <div className="distro-info">
            <div className="distro-name">
              {winpeReady ? '✅ All WinPE files present' : '⚠️ WinPE files incomplete'}
            </div>
            <div className="distro-files">
              <span className={`file-badge${winpeFiles.BCD ? '' : ' file-badge-missing'}`}>
                {winpeFiles.BCD ? '✓' : '✗'} Boot/BCD
              </span>
              <span className={`file-badge${winpeFiles.boot_sdi ? '' : ' file-badge-missing'}`}>
                {winpeFiles.boot_sdi ? '✓' : '✗'} Boot/boot.sdi
              </span>
              <span className={`file-badge${winpeFiles.boot_wim ? '' : ' file-badge-missing'}`}>
                {winpeFiles.boot_wim ? '✓' : '✗'} sources/boot.wim
              </span>
            </div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={fetchStatus} title="Refresh">↻</button>
        </div>

        {!winpeReady && (
          <details className="winpe-instructions">
            <summary className="text-sm">How to prepare WinPE files</summary>
            <ol className="text-sm winpe-steps">
              <li>On a Windows machine, install <strong>Windows ADK</strong> + <strong>WinPE add-on</strong> from Microsoft</li>
              <li>
                Run in Deployment Tools Command Prompt:
                <ul>
                  <li><code>copype amd64 C:\winpe_amd64</code></li>
                </ul>
              </li>
              <li>
                Upload these files (use subfolder as shown):
                <ul>
                  <li><code>winpe_amd64\media\Boot\BCD</code> → subfolder <code>winpe/Boot</code></li>
                  <li><code>winpe_amd64\media\Boot\boot.sdi</code> → subfolder <code>winpe/Boot</code></li>
                  <li><code>winpe_amd64\media\sources\boot.wim</code> → subfolder <code>winpe/sources</code></li>
                </ul>
              </li>
              <li>Add a <strong>Windows PE (wimboot)</strong> entry via the Builder wizard</li>
            </ol>
          </details>
        )}
      </div>
    </section>
  )
}
