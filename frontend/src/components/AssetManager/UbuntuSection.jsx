import { useMemo } from 'react'
import DownloadProgressBlock from './DownloadProgressBlock'
import UrlBadge from './UrlBadge'

export default function UbuntuSection({
  catalog,
  nfsStatus,
  fetchNfsStatus,
  ubuntuVersions,
  selectedUbuntuVersion,
  setSelectedUbuntuVersion,
  ubuntuLoading,
  fetchUbuntuVersions,
  ubuntuDesktopVersions,
  selectedUbuntuDesktopVersion,
  setSelectedUbuntuDesktopVersion,
  ubuntuDesktopLoading,
  fetchUbuntuDesktopVersions,
  downloading,
  downloadProgress,
  downloadStatus,
  checkUrl,
  urlStatus,
  onDownloadUbuntu,
  onDownloadUbuntuDesktop,
}) {
  const installedUbuntuVersions = useMemo(() =>
    new Set((catalog.ubuntu || []).map(d => String(d.version))),
    [catalog.ubuntu]
  )
  const installedDesktopVersions = useMemo(() =>
    new Set((catalog.ubuntu || []).filter(d => d.desktop).map(d => String(d.version))),
    [catalog.ubuntu]
  )

  return (
    <section className="asset-section">
      <h3>🐧 Ubuntu</h3>

      {/* Discovered */}
      {catalog.ubuntu && catalog.ubuntu.length > 0 && (
        <div className="distro-group">
          <h4>📋 Discovered on disk</h4>
          {catalog.ubuntu.map((dist, idx) => (
            <div key={idx} className="distro-item">
              <div className="distro-info">
                <div className="distro-name">✅ Ubuntu {dist.version}</div>
                <div className="distro-files">
                  {dist.kernel && <span className="file-badge">✓ kernel</span>}
                  {dist.initrd && <span className="file-badge">✓ initrd</span>}
                  {dist.iso && <span className="file-badge">✓ ISO</span>}
                  {dist.squashfs && <span className="file-badge">✓ squashfs</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* NFS Boot Status */}
      {catalog.ubuntu && catalog.ubuntu.length > 0 && (
        <div className="distro-group distro-group-nfs">
          <h4>
            📡 NFS Boot
            <button
              className="btn btn-sm btn-secondary nfs-refresh-btn"
              onClick={fetchNfsStatus}
              title="Refresh NFS status"
            >↻ Check</button>
          </h4>
          {!nfsStatus || nfsStatus.loading ? (
            <p className="nfs-text-muted">Checking NFS…</p>
          ) : !nfsStatus.running ? (
            <div className="nfs-text">
              <span className="nfs-status-danger">❌ NFS not running on host</span>
              <span className="nfs-status-note">
                — needed for Ubuntu Server PXE boot
              </span>
              <div className="nfs-command-hint">
                sudo bash scripts/setup-nfs.sh
              </div>
            </div>
          ) : (
            <div className="nfs-text">
              <div className="nfs-status-line">
                <span className="nfs-status-success">✅ NFS running</span>
                {nfsStatus.exports?.length > 0 && (
                  <span className="nfs-status-note">
                    exports: {nfsStatus.exports.join(', ')}
                  </span>
                )}
              </div>
              {catalog.ubuntu.map((dist) => {
                const dir = `ubuntu-${dist.version}`
                const covered = nfsStatus.covered?.includes(dir)
                const serverIp = window.location.hostname
                // Use showmount export, or nfs_root from Settings, or placeholder
                const exportBase = nfsStatus.exports?.[0] || nfsStatus.nfs_root || null
                const nfsroot = exportBase
                  ? `${serverIp}:${exportBase.replace(/\/$/, '')}/${dir}`
                  : null
                const cmdline = nfsroot
                  ? `ip=dhcp boot=casper netboot=nfs nfsroot=${nfsroot}`
                  : null
                return (
                  <div key={dir} className="nfs-entry-card">
                    <div className="nfs-entry-state">
                      {covered
                        ? <span className="nfs-status-success">✅ Ubuntu {dist.version} — export confirmed</span>
                        : cmdline
                          ? <span className="nfs-status-warning">⚠️ Ubuntu {dist.version} — path from Settings, verify manually</span>
                          : <span className="nfs-status-danger">❌ Ubuntu {dist.version} — set NFS Root Path in Settings first</span>
                      }
                    </div>
                    {cmdline ? (
                      <div className="nfs-cmdline-row">
                        <code className="nfs-cmdline-code">
                          {cmdline}
                        </code>
                        <button
                          className="btn btn-sm btn-secondary nfs-copy-btn"
                          onClick={() => {
                            try { navigator.clipboard.writeText(cmdline) } catch {
                              const ta = document.createElement('textarea')
                              ta.value = cmdline
                              document.body.appendChild(ta)
                              ta.select()
                              document.execCommand('copy')
                              document.body.removeChild(ta)
                            }
                          }}
                        >📋 Copy</button>
                      </div>
                    ) : (
                      <div className="nfs-empty-hint">
                        Go to <strong>Settings → NFS Boot</strong> and set the host export path
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Download */}
      <div className="download-section">
        <h4>⬇️ Download</h4>

        {/* Ubuntu Server — dynamic version picker */}
        <div className="download-subsection">
          <h4 className="download-subsection-title">Ubuntu Server (LTS)</h4>
          {ubuntuLoading ? (
            <p className="text-sm text-muted">Loading available versions...</p>
          ) : ubuntuVersions.length > 0 ? (
            <div className="download-picker">
              <label>Version</label>
              <select
                value={selectedUbuntuVersion?.version || ''}
                onChange={(e) => {
                  const v = ubuntuVersions.find(u => u.version === e.target.value)
                  setSelectedUbuntuVersion(v)
                  if (v?.iso_url) checkUrl(v.iso_url)
                }}
              >
                {ubuntuVersions.map(v => (
                  <option key={v.version} value={v.version}>{v.name} ({v.size_est})</option>
                ))}
              </select>
              {selectedUbuntuVersion?.iso_url && (
                <div className="url-badge-wrap">
                  <UrlBadge url={selectedUbuntuVersion.iso_url} urlStatus={urlStatus} />
                </div>
              )}
              {downloading['ubuntu-' + selectedUbuntuVersion?.version] &&
                downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`] && (
                <DownloadProgressBlock
                  title="Ubuntu ISO"
                  progress={downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`]}
                  tone="primary"
                  unit="GB"
                  divisor={1024 * 1024 * 1024}
                  decimals={2}
                />
              )}
              {downloadStatus['ubuntu-' + selectedUbuntuVersion?.version] && (
                <div className="download-status download-picker-progress">
                  {downloadStatus['ubuntu-' + selectedUbuntuVersion?.version]}
                </div>
              )}
              <div className="download-picker-actions">
                <button
                  className="btn btn-primary"
                  onClick={onDownloadUbuntu}
                  disabled={!selectedUbuntuVersion || downloading['ubuntu-' + selectedUbuntuVersion?.version]}
                >
                  {downloading['ubuntu-' + selectedUbuntuVersion?.version]
                    ? '⏳ Downloading...'
                    : installedUbuntuVersions.has(String(selectedUbuntuVersion?.version))
                      ? '🔁 Re-download ISO'
                      : '⬇️ Download ISO'}
                </button>
              </div>
            </div>
          ) : (
            <div>
              <p className="text-sm text-muted download-retry-note">Could not load versions from releases.ubuntu.com</p>
              <button className="btn btn-secondary btn-sm" onClick={fetchUbuntuVersions}>🔄 Retry</button>
            </div>
          )}
        </div>
        {/* Ubuntu Desktop — dynamic version picker */}
        <div className="download-subsection download-subsection-last">
          <h4 className="download-subsection-title">Ubuntu Desktop (LTS)</h4>
          <p className="text-sm text-muted download-retry-note">
            Full GUI live desktop — downloads to <code>ubuntu-{'<ver>'}-desktop/</code> · requires ≥ 8 GB RAM to boot via HTTP ISO
          </p>
          {ubuntuDesktopLoading ? (
            <p className="text-sm text-muted">Loading available versions...</p>
          ) : ubuntuDesktopVersions.length > 0 ? (
            <div className="download-picker">
              <label>Version</label>
              <select
                value={selectedUbuntuDesktopVersion?.version || ''}
                onChange={(e) => {
                  const v = ubuntuDesktopVersions.find(u => u.version === e.target.value)
                  setSelectedUbuntuDesktopVersion(v)
                  if (v?.iso_url) checkUrl(v.iso_url)
                }}
              >
                {ubuntuDesktopVersions.map(v => (
                  <option key={v.version} value={v.version}>{v.name} ({v.size_est})</option>
                ))}
              </select>
              {selectedUbuntuDesktopVersion?.iso_url && (
                <div className="url-badge-wrap">
                  <UrlBadge url={selectedUbuntuDesktopVersion.iso_url} urlStatus={urlStatus} />
                </div>
              )}
              {downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version] &&
                downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`] && (
                <DownloadProgressBlock
                  title="Ubuntu Desktop ISO"
                  progress={downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`]}
                  tone="primary"
                  unit="GB"
                  divisor={1024 * 1024 * 1024}
                  decimals={2}
                  showExtraction
                />
              )}
              {downloadStatus['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version] && (
                <div className="download-status download-picker-progress">
                  {downloadStatus['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version]}
                </div>
              )}
              <div className="download-picker-actions">
                <button
                  className="btn btn-primary"
                  onClick={onDownloadUbuntuDesktop}
                  disabled={!selectedUbuntuDesktopVersion || downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version]}
                >
                  {downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version]
                    ? '⏳ Downloading...'
                    : installedDesktopVersions.has(String(selectedUbuntuDesktopVersion?.version))
                      ? '🔁 Re-download ISO'
                      : '⬇️ Download ISO'}
                </button>
              </div>
            </div>
          ) : (
            <div>
              <p className="text-sm text-muted download-retry-note">Could not load versions from releases.ubuntu.com</p>
              <button className="btn btn-secondary btn-sm" onClick={fetchUbuntuDesktopVersions}>🔄 Retry</button>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
