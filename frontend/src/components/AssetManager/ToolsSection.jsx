import { useMemo } from 'react'
import DownloadProgressBlock from './DownloadProgressBlock'
import UrlBadge from './UrlBadge'

export default function ToolsSection({
  catalog,
  manualToolsRescueFiles,
  deletingAssetPath,
  onDeleteAssetPath,
  systemRescueVersions,
  selectedSysrescueVersion,
  setSelectedSysrescueVersion,
  kasperskyVersions,
  selectedKasperskyVersion,
  setSelectedKasperskyVersion,
  hirenVersions,
  selectedHirenVersion,
  setSelectedHirenVersion,
  downloading,
  downloadProgress,
  downloadStatus,
  checkUrl,
  urlStatus,
  onDownloadSystemRescue,
  onDownloadKaspersky,
  onDownloadHiren,
}) {
  const installedSystemRescueVersions = useMemo(() => {
    const rows = Array.isArray(catalog.rescue) ? catalog.rescue : []
    return new Set(rows.map(row => String(row.version)))
  }, [catalog.rescue])

  const installedKasperskyVersions = useMemo(() => {
    const rows = Array.isArray(catalog.kaspersky) ? catalog.kaspersky : []
    return new Set(rows.map(row => String(row.version)))
  }, [catalog.kaspersky])

  const installedHirenVersions = useMemo(() => {
    const rows = Array.isArray(catalog.hiren) ? catalog.hiren : []
    return new Set(rows.map(row => String(row.version)))
  }, [catalog.hiren])

  return (
    <section className="asset-section">
      <h3>🛠️ Tools &amp; Rescue</h3>

      {manualToolsRescueFiles.length > 0 && (
        <div className="distro-group">
          <h4>📂 Manual files (categorized)</h4>
          {manualToolsRescueFiles.map(({ path, category }) => (
            <div key={path} className="distro-item">
              <div className="distro-info">
                <div className="distro-name">
                  📄 {path.split('/').at(-1) || path}
                  <span className="file-badge">category: {category}</span>
                </div>
              </div>
              <button
                className="btn btn-danger btn-sm"
                onClick={() => onDeleteAssetPath(path)}
                disabled={deletingAssetPath === path}
                title={`Delete ${path}`}
              >
                {deletingAssetPath === path ? '⏳ Deleting...' : '🗑️ Delete'}
              </button>
            </div>
          ))}
        </div>
      )}

      {catalog.rescue && catalog.rescue.length > 0 && (
        <div className="distro-group">
          <h4>📋 Discovered on disk</h4>
          {catalog.rescue.map((dist, idx) => (
            <div key={idx} className="distro-item">
              <div className="distro-info">
                <div className="distro-name">✅ SystemRescue {dist.version}</div>
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

      {/* SystemRescue */}
      <div className="download-subsection">
        <h4>🛟 SystemRescue</h4>
        <p className="text-sm text-muted download-section-note">
          Select a version to download
        </p>
          {systemRescueVersions.length > 0 ? (
            <div className="download-picker">
              <label>Version</label>
              <select
                value={selectedSysrescueVersion?.version || ''}
                onChange={(e) => {
                  const version = systemRescueVersions.find(v => v.version === e.target.value)
                  setSelectedSysrescueVersion(version)
                  if (version?.iso_url) checkUrl(version.iso_url)
                }}
              >
                {systemRescueVersions.map(v => (
                  <option key={v.version} value={v.version}>{v.name} ({v.size_est})</option>
                ))}
              </select>
              {selectedSysrescueVersion?.iso_url && (
                <div className="url-badge-wrap">
                  <UrlBadge url={selectedSysrescueVersion.iso_url} urlStatus={urlStatus} />
                </div>
              )}
              {downloading['systemrescue-' + selectedSysrescueVersion?.version] && downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`] && (
                <DownloadProgressBlock
                  title="SystemRescue ISO"
                  progress={downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`]}
                  tone="success"
                  unit="GB"
                  divisor={1024 * 1024 * 1024}
                  decimals={2}
                  showExtraction
                />
              )}
              {downloadStatus['systemrescue-' + selectedSysrescueVersion?.version] && (
                <div className="download-status download-picker-progress">
                  {downloadStatus['systemrescue-' + selectedSysrescueVersion?.version]}
                </div>
              )}
              <div className="download-picker-actions">
                <button
                  className="btn btn-primary"
                  onClick={onDownloadSystemRescue}
                  disabled={!selectedSysrescueVersion || downloading['systemrescue-' + selectedSysrescueVersion?.version]}
                >
                  {downloading['systemrescue-' + selectedSysrescueVersion?.version]
                    ? '⏳ Downloading...'
                    : installedSystemRescueVersions.has(String(selectedSysrescueVersion?.version))
                      ? '🔁 Re-download ISO'
                      : '⬇️ Download ISO'}
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">Loading versions...</p>
        )}
      </div>

      {catalog.kaspersky && catalog.kaspersky.length > 0 && (
        <div className="distro-group">
          <h4>📋 Discovered on disk</h4>
          {catalog.kaspersky.map((dist, idx) => (
            <div key={idx} className="distro-item">
              <div className="distro-info">
                <div className="distro-name">✅ Kaspersky Rescue Disk {dist.version}</div>
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

      {/* Kaspersky Rescue Disk */}
      <div className="download-subsection">
        <h4>🛡️ Kaspersky Rescue Disk</h4>
        <p className="text-sm text-muted download-section-note">
          Select a version to download (ISO will be extracted automatically)
        </p>
        {kasperskyVersions.length > 0 ? (
          <div className="download-picker">
            <label>Version</label>
            <select
              value={selectedKasperskyVersion?.version || ''}
              onChange={(e) => {
                const version = kasperskyVersions.find(v => v.version === e.target.value)
                setSelectedKasperskyVersion(version)
                if (version?.iso_url) checkUrl(version.iso_url)
              }}
            >
              {kasperskyVersions.map(v => (
                <option key={v.version} value={v.version}>{v.name} ({v.size_est})</option>
              ))}
            </select>
            {selectedKasperskyVersion?.notes && (
              <div className="kaspersky-note">
                ℹ️ {selectedKasperskyVersion.notes}
              </div>
            )}
            {selectedKasperskyVersion?.iso_url && (
              <div className="url-badge-wrap">
                <UrlBadge url={selectedKasperskyVersion.iso_url} urlStatus={urlStatus} />
              </div>
            )}
            {downloading['kaspersky-' + selectedKasperskyVersion?.version] && downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`] && (
              <DownloadProgressBlock
                title="Kaspersky ISO"
                progress={downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`]}
                tone="warning"
                unit="MB"
                divisor={1024 * 1024}
                decimals={0}
                showExtraction
                extractingTone="warning"
              />
            )}
            {downloadStatus['kaspersky-' + selectedKasperskyVersion?.version] && (
              <div className="download-status download-picker-progress">
                {downloadStatus['kaspersky-' + selectedKasperskyVersion?.version]}
              </div>
            )}
            <div className="download-picker-actions">
              <button
                className="btn btn-primary"
                onClick={onDownloadKaspersky}
                disabled={!selectedKasperskyVersion || downloading['kaspersky-' + selectedKasperskyVersion?.version]}
              >
                {downloading['kaspersky-' + selectedKasperskyVersion?.version]
                  ? '⏳ Downloading...'
                  : installedKasperskyVersions.has(String(selectedKasperskyVersion?.version))
                    ? '🔁 Re-download ISO'
                    : '⬇️ Download ISO'}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">Loading versions...</p>
        )}
      </div>

      {catalog.hiren && catalog.hiren.length > 0 && (
        <div className="distro-group">
          <h4>📋 Discovered on disk</h4>
          {catalog.hiren.map((dist, idx) => (
            <div key={idx} className="distro-item">
              <div className="distro-info">
                <div className="distro-name">✅ Hiren&apos;s BootCD PE {dist.version}</div>
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

      {/* Modern Hiren's BootCD PE */}
      <div className="download-subsection">
        <h4>🧰 Hiren&apos;s BootCD PE (Modern)</h4>
        <p className="text-sm text-muted download-section-note">
          Select a version to download
        </p>
        {hirenVersions.length > 0 ? (
          <div className="download-picker">
            <label>Version</label>
            <select
              value={selectedHirenVersion?.version || ''}
              onChange={(e) => {
                const version = hirenVersions.find(v => v.version === e.target.value)
                setSelectedHirenVersion(version)
                if (version?.iso_url) checkUrl(version.iso_url)
              }}
            >
              {hirenVersions.map(v => (
                <option key={v.version} value={v.version}>{v.name} ({v.size_est})</option>
              ))}
            </select>
            {selectedHirenVersion?.notes && (
              <div className="kaspersky-note">
                ℹ️ {selectedHirenVersion.notes}
              </div>
            )}
            {selectedHirenVersion?.iso_url && (
              <div className="url-badge-wrap">
                <UrlBadge url={selectedHirenVersion.iso_url} urlStatus={urlStatus} />
              </div>
            )}
            {downloading['hiren-' + selectedHirenVersion?.version] && downloadProgress[`${selectedHirenVersion?.dest_folder || `hiren-${selectedHirenVersion?.version}`}/${selectedHirenVersion?.iso_name}`] && (
              <DownloadProgressBlock
                title="Hiren ISO"
                progress={downloadProgress[`${selectedHirenVersion?.dest_folder || `hiren-${selectedHirenVersion?.version}`}/${selectedHirenVersion?.iso_name}`]}
                tone="primary"
                unit="GB"
                divisor={1024 * 1024 * 1024}
                decimals={2}
                showExtraction
              />
            )}
            {downloadStatus['hiren-' + selectedHirenVersion?.version] && (
              <div className="download-status download-picker-progress">
                {downloadStatus['hiren-' + selectedHirenVersion?.version]}
              </div>
            )}
            <div className="download-picker-actions">
              <button
                className="btn btn-primary"
                onClick={onDownloadHiren}
                disabled={!selectedHirenVersion || downloading['hiren-' + selectedHirenVersion?.version]}
              >
                {downloading['hiren-' + selectedHirenVersion?.version]
                  ? '⏳ Downloading...'
                  : installedHirenVersions.has(String(selectedHirenVersion?.version))
                    ? '🔁 Re-download ISO'
                    : '⬇️ Download ISO'}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">Loading versions...</p>
        )}
      </div>

      <div className="download-subsection">
        <h4>🧩 GParted Live</h4>
        <p className="text-sm text-muted download-section-note">
          Official source links for latest ISO and PXE workflow.
        </p>
        <div className="download-picker-actions">
          <a
            className="btn btn-secondary btn-sm"
            href="https://gparted.org/download.php"
            target="_blank"
            rel="noreferrer"
          >
            🌐 Official Download
          </a>
          <a
            className="btn btn-secondary btn-sm"
            href="https://gparted.org/livepxe.php"
            target="_blank"
            rel="noreferrer"
          >
            📘 PXE Docs
          </a>
        </div>
      </div>

      <div className="download-subsection download-subsection-last">
        <h4>🧪 Clonezilla Live</h4>
        <p className="text-sm text-muted download-section-note">
          Official source links for latest ISO and PXE workflow.
        </p>
        <div className="download-picker-actions">
          <a
            className="btn btn-secondary btn-sm"
            href="https://clonezilla.org/downloads.php"
            target="_blank"
            rel="noreferrer"
          >
            🌐 Official Download
          </a>
          <a
            className="btn btn-secondary btn-sm"
            href="https://clonezilla.org/livepxe.php"
            target="_blank"
            rel="noreferrer"
          >
            📘 PXE Docs
          </a>
        </div>
      </div>
    </section>
  )
}
