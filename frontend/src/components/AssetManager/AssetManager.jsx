import { useState, useEffect } from 'react'
import './AssetManager.css'

function AssetManager() {
  const [assets, setAssets] = useState({ http: [], tftp: [], ipxe: [] })
  const [catalog, setCatalog] = useState({ ubuntu: [], debian: [], windows: [], rescue: [] })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchAssets()
    fetchCatalog()
  }, [])

  const fetchAssets = async () => {
    try {
      const response = await fetch('/api/assets')
      const data = await response.json()
      setAssets(data)
    } catch (error) {
      console.error('Failed to fetch assets:', error)
    }
  }

  const fetchCatalog = async () => {
    try {
      const response = await fetch('/api/assets/catalog')
      const data = await response.json()
      setCatalog(data)
    } catch (error) {
      console.error('Failed to fetch catalog:', error)
    }
  }

  return (
    <div className="asset-manager">
      <div className="asset-header">
        <h2>Asset Manager</h2>
        <div className="asset-actions">
          <button className="btn btn-secondary" onClick={fetchCatalog}>
            🔄 Scan
          </button>
          <button className="btn btn-primary">
            📁 Upload Files
          </button>
        </div>
      </div>

      <div className="asset-content">
        {/* Discovered Distributions */}
        <section className="asset-section">
          <h3>📊 Discovered Distributions</h3>

          {/* Ubuntu */}
          {catalog.ubuntu && catalog.ubuntu.length > 0 && (
            <div className="distro-group">
              <h4>🐧 Ubuntu</h4>
              {catalog.ubuntu.map((dist, idx) => (
                <div key={idx} className="distro-item">
                  <div className="distro-info">
                    <div className="distro-name">
                      ✅ Ubuntu {dist.version}
                    </div>
                    <div className="distro-files">
                      {dist.kernel && <span className="file-badge">✓ kernel</span>}
                      {dist.initrd && <span className="file-badge">✓ initrd</span>}
                      {dist.iso && <span className="file-badge">✓ ISO</span>}
                    </div>
                  </div>
                  <div className="distro-actions">
                    <button className="btn btn-secondary btn-sm">Use in Menu</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Debian */}
          {catalog.debian && catalog.debian.length > 0 && (
            <div className="distro-group">
              <h4>🌀 Debian</h4>
              {catalog.debian.map((dist, idx) => (
                <div key={idx} className="distro-item">
                  <div className="distro-info">
                    <div className="distro-name">
                      ✅ Debian {dist.version}
                    </div>
                    <div className="distro-files">
                      {dist.kernel && <span className="file-badge">✓ kernel</span>}
                      {dist.initrd && <span className="file-badge">✓ initrd</span>}
                    </div>
                  </div>
                  <div className="distro-actions">
                    <button className="btn btn-secondary btn-sm">Use in Menu</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Quick Download Section */}
          <div className="download-section">
            <h4>⬇️ Quick Download</h4>
            <div className="download-grid">
              <div className="download-card">
                <div className="download-name">Ubuntu 22.04 LTS</div>
                <div className="download-size">~2.8 GB</div>
                <button className="btn btn-primary btn-sm">Download</button>
              </div>
              <div className="download-card">
                <div className="download-name">Ubuntu 24.04 LTS</div>
                <div className="download-size">~2.9 GB</div>
                <button className="btn btn-primary btn-sm">Download</button>
              </div>
              <div className="download-card">
                <div className="download-name">Debian 12</div>
                <div className="download-size">~50 MB</div>
                <button className="btn btn-primary btn-sm">Download</button>
              </div>
              <div className="download-card">
                <div className="download-name">SystemRescue</div>
                <div className="download-size">~800 MB</div>
                <button className="btn btn-primary btn-sm">Download</button>
              </div>
            </div>
          </div>
        </section>

        {/* All Files */}
        <section className="asset-section">
          <h3>📁 All Files</h3>
          <div className="file-tree">
            <div className="file-tree-header">/srv/http/</div>
            {assets.http && assets.http.length > 0 ? (
              <ul className="file-list">
                {assets.http.slice(0, 20).map((file, idx) => (
                  <li key={idx} className="file-item">
                    <span className="file-icon">📄</span>
                    <span className="file-name">{file}</span>
                  </li>
                ))}
                {assets.http.length > 20 && (
                  <li className="file-item text-muted">
                    ... and {assets.http.length - 20} more files
                  </li>
                )}
              </ul>
            ) : (
              <div className="empty-state">
                <p className="text-muted">No files found</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

export default AssetManager
