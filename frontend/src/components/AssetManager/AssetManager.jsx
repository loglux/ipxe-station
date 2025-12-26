import { useState, useEffect } from 'react'
import './AssetManager.css'

// Downloadable distros with URLs and menu configurations
const DOWNLOADABLE_DISTROS = [
  {
    id: 'ubuntu-24.04',
    name: 'Ubuntu 24.04 LTS (Noble)',
    kernel_url: 'http://archive.ubuntu.com/ubuntu/dists/noble/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/linux',
    initrd_url: 'http://archive.ubuntu.com/ubuntu/dists/noble/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/initrd.gz',
    iso_url: 'https://releases.ubuntu.com/24.04/ubuntu-24.04.1-live-server-amd64.iso',
    dest_folder: 'ubuntu-24.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd', iso: 'ubuntu-24.04-live-server-amd64.iso' },
    size: '~70 MB',
    iso_size: '~2.6 GB',
    supports_iso: true,
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      cmdline: 'ip=dhcp url=http://${server_ip}:${port}/ubuntu-24.04/',
      requires_internet: true
    }
  },
  {
    id: 'ubuntu-22.04',
    name: 'Ubuntu 22.04 LTS (Jammy)',
    kernel_url: 'http://archive.ubuntu.com/ubuntu/dists/jammy/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/linux',
    initrd_url: 'http://archive.ubuntu.com/ubuntu/dists/jammy/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/initrd.gz',
    iso_url: 'https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso',
    dest_folder: 'ubuntu-22.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd', iso: 'ubuntu-22.04-live-server-amd64.iso' },
    size: '~70 MB',
    iso_size: '~2.4 GB',
    supports_iso: true,
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      cmdline: 'ip=dhcp url=http://${server_ip}:${port}/ubuntu-22.04/',
      requires_internet: true
    }
  },
  {
    id: 'ubuntu-20.04',
    name: 'Ubuntu 20.04 LTS (Focal)',
    kernel_url: 'http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/linux',
    initrd_url: 'http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/initrd.gz',
    iso_url: 'https://releases.ubuntu.com/20.04/ubuntu-20.04.6-live-server-amd64.iso',
    dest_folder: 'ubuntu-20.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd', iso: 'ubuntu-20.04-live-server-amd64.iso' },
    size: '~60 MB',
    iso_size: '~1.3 GB',
    supports_iso: true,
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      cmdline: 'ip=dhcp url=http://${server_ip}:${port}/ubuntu-20.04/',
      requires_internet: true
    }
  },
  {
    id: 'debian-13',
    name: 'Debian 13 (Trixie) Testing',
    kernel_url: 'http://deb.debian.org/debian/dists/trixie/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux',
    initrd_url: 'http://deb.debian.org/debian/dists/trixie/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz',
    dest_folder: 'debian-13',
    files: { kernel: 'vmlinuz', initrd: 'initrd' },
    size: '~45 MB',
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      cmdline: 'ip=dhcp',
      requires_internet: true
    }
  },
  {
    id: 'debian-12',
    name: 'Debian 12 (Bookworm) Stable',
    kernel_url: 'http://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux',
    initrd_url: 'http://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz',
    dest_folder: 'debian-12',
    files: { kernel: 'vmlinuz', initrd: 'initrd' },
    size: '~45 MB',
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      cmdline: 'ip=dhcp',
      requires_internet: true
    }
  },
  {
    id: 'debian-11',
    name: 'Debian 11 (Bullseye) OldStable',
    kernel_url: 'http://deb.debian.org/debian/dists/bullseye/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux',
    initrd_url: 'http://deb.debian.org/debian/dists/bullseye/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz',
    dest_folder: 'debian-11',
    files: { kernel: 'vmlinuz', initrd: 'initrd' },
    size: '~40 MB',
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      cmdline: 'ip=dhcp',
      requires_internet: true
    }
  },
]

// SystemRescue is handled separately with version selection
const SYSTEMRESCUE_CONFIG = {
  id: 'systemrescue',
  name: 'SystemRescue',
  dest_folder: 'rescue',
  dynamic_versions: true
}

function AssetManager() {
  const [assets, setAssets] = useState({ http: [], tftp: [], ipxe: [] })
  const [catalog, setCatalog] = useState({ ubuntu: [], debian: [], windows: [], rescue: [] })
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState({})
  const [downloadStatus, setDownloadStatus] = useState({})
  const [downloadProgress, setDownloadProgress] = useState({}) // Track download progress percentages
  const [downloadIso, setDownloadIso] = useState({}) // Track ISO download option for each distro
  const [systemRescueVersions, setSystemRescueVersions] = useState([])
  const [selectedSysrescueVersion, setSelectedSysrescueVersion] = useState(null)

  useEffect(() => {
    fetchAssets()
    fetchCatalog()
    fetchSystemRescueVersions()
  }, [])

  // Poll for download progress
  useEffect(() => {
    const pollProgress = async () => {
      try {
        const response = await fetch('/api/assets/download/progress')
        const data = await response.json()
        if (data.downloads) {
          setDownloadProgress(data.downloads)

          // Auto-detect active downloads and update downloading state
          const activeDownloads = {}
          Object.keys(data.downloads).forEach(key => {
            if (data.downloads[key].status === 'downloading') {
              // Try to match to a distro ID
              DOWNLOADABLE_DISTROS.forEach(distro => {
                if (key.includes(distro.dest_folder)) {
                  activeDownloads[distro.id] = true
                }
              })
            }
          })

          // Update downloading state if we found active downloads
          if (Object.keys(activeDownloads).length > 0) {
            setDownloading(prev => ({ ...prev, ...activeDownloads }))
          }
        }
      } catch (error) {
        console.error('Failed to fetch progress:', error)
      }
    }

    // Check immediately on mount
    pollProgress()

    // Poll every 2 seconds if there are active downloads OR we just mounted
    const hasActiveDownloads = Object.keys(downloading).some(key => downloading[key]) ||
                               Object.keys(downloadProgress).some(key => downloadProgress[key]?.status === 'downloading')

    if (hasActiveDownloads) {
      const interval = setInterval(pollProgress, 2000)
      return () => clearInterval(interval)
    }
  }, [downloading, downloadProgress])

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

  const fetchSystemRescueVersions = async () => {
    try {
      const response = await fetch('/api/assets/versions/systemrescue')
      const data = await response.json()
      setSystemRescueVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedSysrescueVersion(data.versions[0]) // Select latest by default
      }
    } catch (error) {
      console.error('Failed to fetch SystemRescue versions:', error)
    }
  }

  const downloadDistro = async (distro) => {
    setDownloading(prev => ({ ...prev, [distro.id]: true }))
    const includeIso = downloadIso[distro.id] || false

    try {
      // Always download kernel + initrd (unless ISO-only)
      if (!distro.iso_only) {
        setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading kernel...' }))
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
          const error = await kernelResponse.json()
          throw new Error(error.detail || 'Failed to download kernel')
        }

        setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading initrd...' }))
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
          const error = await initrdResponse.json()
          throw new Error(error.detail || 'Failed to download initrd')
        }
      }

      // Download ISO if requested (or if ISO-only distro)
      if (distro.iso_only || (distro.supports_iso && includeIso)) {
        setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading ISO... (this may take a while)' }))
        const isoDest = `${distro.dest_folder}/${distro.files.iso}`
        const isoUrl = distro.iso_only ? distro.kernel_url : distro.iso_url

        const isoResponse = await fetch('/api/assets/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: isoUrl,
            dest: isoDest
          })
        })

        if (!isoResponse.ok) {
          const error = await isoResponse.json()
          throw new Error(error.detail || 'Failed to download ISO')
        }
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
      }, 5000)
    } finally {
      setDownloading(prev => ({ ...prev, [distro.id]: false }))
    }
  }

  const downloadSystemRescue = async () => {
    if (!selectedSysrescueVersion) return

    const distroId = 'systemrescue-' + selectedSysrescueVersion.version
    setDownloading(prev => ({ ...prev, [distroId]: true }))

    try {
      setDownloadStatus(prev => ({ ...prev, [distroId]: 'Downloading ISO... (this may take a while)' }))
      const isoDest = `${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion.iso_name}`

      const isoResponse = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: selectedSysrescueVersion.iso_url,
          dest: isoDest
        })
      })

      if (!isoResponse.ok) {
        const error = await isoResponse.json()
        throw new Error(error.detail || 'Failed to download ISO')
      }

      setDownloadStatus(prev => ({ ...prev, [distroId]: '✅ Downloaded!' }))

      setTimeout(() => {
        fetchCatalog()
        setDownloadStatus(prev => ({ ...prev, [distroId]: '' }))
      }, 2000)

    } catch (error) {
      setDownloadStatus(prev => ({ ...prev, [distroId]: `❌ Error: ${error.message}` }))
      setTimeout(() => {
        setDownloadStatus(prev => ({ ...prev, [distroId]: '' }))
      }, 5000)
    } finally {
      setDownloading(prev => ({ ...prev, [distroId]: false }))
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
                  <div className="download-size">{distro.size}</div>

                  {distro.supports_iso && (
                    <label style={{ fontSize: '12px', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <input
                        type="checkbox"
                        checked={downloadIso[distro.id] || false}
                        onChange={(e) => setDownloadIso(prev => ({ ...prev, [distro.id]: e.target.checked }))}
                      />
                      Also download ISO ({distro.iso_size})
                    </label>
                  )}

                  {/* Progress bar for active downloads */}
                  {downloading[distro.id] && downloadProgress[`${distro.dest_folder}/vmlinuz`] && (
                    <div style={{ marginTop: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                        <span>{downloadProgress[`${distro.dest_folder}/vmlinuz`].percentage}%</span>
                        <span>{(downloadProgress[`${distro.dest_folder}/vmlinuz`].downloaded / 1024 / 1024).toFixed(1)} MB / {(downloadProgress[`${distro.dest_folder}/vmlinuz`].total / 1024 / 1024).toFixed(1)} MB</span>
                      </div>
                      <div style={{ width: '100%', height: '4px', background: '#e5e7eb', borderRadius: '2px', overflow: 'hidden' }}>
                        <div style={{ width: `${downloadProgress[`${distro.dest_folder}/vmlinuz`].percentage}%`, height: '100%', background: '#3b82f6', transition: 'width 0.3s' }}></div>
                      </div>
                    </div>
                  )}

                  {downloadStatus[distro.id] && (
                    <div className="download-status">{downloadStatus[distro.id]}</div>
                  )}
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => downloadDistro(distro)}
                    disabled={downloading[distro.id]}
                    title={distro.supports_iso ? 'Download kernel + initrd' + (downloadIso[distro.id] ? ' + ISO' : '') : 'Download kernel + initrd'}
                  >
                    {downloading[distro.id] ? '⏳ Downloading...' : '⬇️ Download'}
                  </button>
                </div>
              ))}
            </div>

            {/* SystemRescue Version Selector */}
            <div style={{ marginTop: '32px', paddingTop: '24px', borderTop: '1px solid var(--color-border)' }}>
              <h4>🛟 SystemRescue</h4>
              <p className="text-sm text-muted" style={{ marginBottom: '16px' }}>
                Select a version to download
              </p>
              {systemRescueVersions.length > 0 ? (
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: 'block', fontSize: '13px', marginBottom: '4px', fontWeight: '500' }}>
                      Version
                    </label>
                    <select
                      style={{
                        width: '100%',
                        padding: '8px',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--color-border)',
                        fontSize: '14px'
                      }}
                      value={selectedSysrescueVersion?.version || ''}
                      onChange={(e) => {
                        const version = systemRescueVersions.find(v => v.version === e.target.value)
                        setSelectedSysrescueVersion(version)
                      }}
                    >
                      {systemRescueVersions.map(v => (
                        <option key={v.version} value={v.version}>
                          {v.name} ({v.size_est})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div style={{ minWidth: '300px' }}>
                    {/* Progress bar for SystemRescue */}
                    {downloading['systemrescue-' + selectedSysrescueVersion?.version] && downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`] && (
                      <div style={{ marginBottom: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                          <span>{downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].percentage}%</span>
                          <span>{(downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].downloaded / 1024 / 1024).toFixed(1)} MB / {(downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].total / 1024 / 1024).toFixed(1)} MB</span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: '#e5e7eb', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].percentage}%`, height: '100%', background: '#10b981', transition: 'width 0.3s' }}></div>
                        </div>
                      </div>
                    )}

                    {downloadStatus['systemrescue-' + selectedSysrescueVersion?.version] && (
                      <div className="download-status" style={{ marginBottom: '8px' }}>
                        {downloadStatus['systemrescue-' + selectedSysrescueVersion?.version]}
                      </div>
                    )}
                    <button
                      className="btn btn-primary"
                      onClick={downloadSystemRescue}
                      disabled={!selectedSysrescueVersion || downloading['systemrescue-' + selectedSysrescueVersion?.version]}
                    >
                      {downloading['systemrescue-' + selectedSysrescueVersion?.version] ? '⏳ Downloading...' : '⬇️ Download ISO'}
                    </button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted">Loading versions...</p>
              )}
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
