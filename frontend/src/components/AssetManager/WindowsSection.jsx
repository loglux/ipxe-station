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
  const winpeReady = winpeFiles.bootmgr && winpeFiles.BCD && winpeFiles.boot_sdi && winpeFiles.boot_wim

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
          Extract these from a Windows installation ISO and place in <code>/srv/http/winpe/</code>.
          Use the <strong>Upload File</strong> button above to upload each file.
        </p>

        <div className="distro-item">
          <div className="distro-info">
            <div className="distro-name">
              {winpeReady ? '✅ All WinPE files present' : '⚠️ WinPE files incomplete'}
            </div>
            <div className="distro-files">
              <span className={`file-badge${winpeFiles.bootmgr ? '' : ' file-badge-missing'}`}>
                {winpeFiles.bootmgr ? '✓' : '✗'} bootmgr
              </span>
              <span className={`file-badge${winpeFiles.BCD ? '' : ' file-badge-missing'}`}>
                {winpeFiles.BCD ? '✓' : '✗'} BCD
              </span>
              <span className={`file-badge${winpeFiles.boot_sdi ? '' : ' file-badge-missing'}`}>
                {winpeFiles.boot_sdi ? '✓' : '✗'} boot.sdi
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
            <summary className="text-sm">How to extract WinPE files from a Windows ISO</summary>
            <ol className="text-sm winpe-steps">
              <li>Mount or extract the Windows installation ISO</li>
              <li>
                Copy these files to <code>/srv/http/winpe/</code>:
                <ul>
                  <li><code>bootmgr</code> — from ISO root</li>
                  <li><code>BCD</code> — from <code>Boot/BCD</code></li>
                  <li><code>boot.sdi</code> — from <code>Boot/boot.sdi</code></li>
                  <li><code>sources/boot.wim</code> — keep in <code>sources/</code> subfolder</li>
                </ul>
              </li>
              <li>Use <strong>Upload File</strong> above, set subfolder to <code>winpe</code> or <code>winpe/sources</code></li>
              <li>Then add a <strong>Windows PE (WIMBoot)</strong> entry via the Builder wizard</li>
            </ol>
          </details>
        )}
      </div>
    </section>
  )
}
