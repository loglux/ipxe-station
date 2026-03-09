import DownloadProgressBlock from './DownloadProgressBlock'
import UrlBadge from './UrlBadge'

export default function DebianSection({
  catalog,
  debianProducts,
  downloading,
  downloadProgress,
  downloadStatus,
  urlStatus,
  onDownloadDistro,
}) {
  return (
    <section className="asset-section">
      <h3>🌀 Debian</h3>

      {catalog.debian && catalog.debian.length > 0 && (
        <div className="distro-group">
          <h4>📋 Discovered on disk</h4>
          {catalog.debian.map((dist, idx) => (
            <div key={idx} className="distro-item">
              <div className="distro-info">
                <div className="distro-name">✅ Debian {dist.version}</div>
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

      <div className="download-section">
        <h4>⬇️ Download</h4>
        <div className="download-subsection download-subsection-last">
          <p className="text-sm text-muted download-section-note">
            Installer bootstrap, netinst ISO, and live ISO from official Debian sources.
          </p>
          <div className="download-grid">
            {debianProducts.map(distro => (
              <div key={distro.id} className="download-card">
                <div className="download-name">{distro.name}</div>
                <div className="download-size">{distro.size_est}</div>
                <div className="download-description">{distro.description}</div>
                <div className="download-uses">
                  Unlocks: {distro.boot_targets.join(', ')}
                  {distro.experimental ? ' · Experimental' : ''}
                </div>

                {distro.iso_url && (
                  <div className="download-card-url">
                    <UrlBadge url={distro.iso_url} urlStatus={urlStatus} />
                  </div>
                )}

                {downloading[distro.id] && (
                  <div className="download-card-progress">
                    {distro.files.kernel && downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`] && (
                      <DownloadProgressBlock
                        title="linux"
                        progress={downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`]}
                        tone="primary"
                        unit="MB"
                        divisor={1024 * 1024}
                        decimals={1}
                      />
                    )}

                    {distro.files.initrd && downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`] && (
                      <DownloadProgressBlock
                        title="initrd.gz"
                        progress={downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`]}
                        tone="primary"
                        unit="MB"
                        divisor={1024 * 1024}
                        decimals={1}
                      />
                    )}

                    {distro.files.iso && downloadProgress[`${distro.dest_folder}/${distro.files.iso}`] && (
                      <DownloadProgressBlock
                        title="ISO"
                        progress={downloadProgress[`${distro.dest_folder}/${distro.files.iso}`]}
                        tone="success"
                        unit="GB"
                        divisor={1024 * 1024 * 1024}
                        decimals={2}
                        showExtraction
                      />
                    )}
                  </div>
                )}

                {downloadStatus[distro.id] && (
                  <div className="download-status">{downloadStatus[distro.id]}</div>
                )}
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => onDownloadDistro(distro)}
                  disabled={downloading[distro.id]}
                  title={distro.iso_only ? 'Download Debian ISO' : 'Download Debian installer files'}
                >
                  {downloading[distro.id] ? '⏳ Downloading...' : distro.iso_only ? '⬇️ Download ISO' : '⬇️ Download Installer Files'}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
