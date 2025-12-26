import { useState, useEffect } from 'react'
import './AssetManager.css'

// Downloadable distros with URLs
const DOWNLOADABLE_DISTROS = [
  {
    id: 'ubuntu-24.04',
    name: 'Ubuntu 24.04 LTS',
    kernel_url: 'http://archive.ubuntu.com/ubuntu/dists/noble/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/linux',
    initrd_url: 'http://archive.ubuntu.com/ubuntu/dists/noble/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/initrd.gz',
    dest_folder: 'ubuntu-24.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd' }
  },
  {
    id: 'ubuntu-22.04',
    name: 'Ubuntu 22.04 LTS',
    kernel_url: 'http://archive.ubuntu.com/ubuntu/dists/jammy/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/linux',
    initrd_url: 'http://archive.ubuntu.com/ubuntu/dists/jammy/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/initrd.gz',
    dest_folder: 'ubuntu-22.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd' }
  },
  {
    id: 'ubuntu-20.04',
    name: 'Ubuntu 20.04 LTS',
    kernel_url: 'http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/linux',
    initrd_url: 'http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/initrd.gz',
    dest_folder: 'ubuntu-20.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd' }
  },
  {
    id: 'debian-12',
    name: 'Debian 12 (Bookworm)',
    kernel_url: 'http://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux',
    initrd_url: 'http://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz',
    dest_folder: 'debian-12',
    files: { kernel: 'vmlinuz', initrd: 'initrd' }
  }
]

function AssetManager() {
  const [assets, setAssets] = useState({ http: [], tftp: [], ipxe: [] })
  const [catalog, setCatalog] = useState({ ubuntu: [], debian: [], windows: [], rescue: [] })
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState({})
  const [downloadStatus, setDownloadStatus] = useState({})

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

  const downloadDistro = async (distro) => {
    setDownloading(prev => ({ ...prev, [distro.id]: true }))
    setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading kernel...' }))

    try {
      // Download kernel
      const kernelDest = `${distro.dest_folder}/${distro.files.kernel}`
      const kernelResponse = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: distro.kernel_url,
          dest: kernelDest
        })
      })

      if (!kernelResponse.ok) {
        throw new Error('Failed to download kernel')
      }

      setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading initrd...' }))

      // Download initrd
      const initrdDest = `${distro.dest_folder}/${distro.files.initrd}`
      const initrdResponse = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: distro.initrd_url,
          dest: initrdDest
        })
      })

      if (!initrdResponse.ok) {
        throw new Error('Failed to download initrd')
      }

      setDownloadStatus(prev => ({ ...prev, [distro.id]: '✅ Downloaded!' }))

      // Refresh catalog after successful download
      setTimeout(() => {
        fetchCatalog()
        setDownloadStatus(prev => ({ ...prev, [distro.id]: '' }))
      }, 2000)

    } catch (error) {
      setDownloadStatus(prev => ({ ...prev, [distro.id]: `❌ Error: ${error.message}` }))
      setTimeout(() => {
        setDownloadStatus(prev => ({ ...prev, [distro.id]: '' }))
      }, 3000)
    } finally {
      setDownloading(prev => ({ ...prev, [distro.id]: false }))
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
            <p className="text-sm text-muted" style={{ marginBottom: '16px' }}>
              Download netboot files (kernel + initrd) for network installation
            </p>
            <div className="download-grid">
              {DOWNLOADABLE_DISTROS.map(distro => (
                <div key={distro.id} className="download-card">
                  <div className="download-name">{distro.name}</div>
                  <div className="download-size">~50 MB</div>
                  {downloadStatus[distro.id] && (
                    <div className="download-status">{downloadStatus[distro.id]}</div>
                  )}
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => downloadDistro(distro)}
                    disabled={downloading[distro.id]}
                  >
                    {downloading[distro.id] ? '⏳ Downloading...' : '⬇️ Download'}
                  </button>
                </div>
              ))}
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
