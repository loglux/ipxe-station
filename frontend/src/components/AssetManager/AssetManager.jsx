import { useState, useEffect, useCallback, useRef } from 'react'
import './AssetManager.css'

// Downloadable distros with URLs and menu configurations
const DOWNLOADABLE_DISTROS = [
  {
    id: 'ubuntu-24.04',
    name: 'Ubuntu 24.04 LTS (Noble)',
    // No netboot images available for 24.04 - use ISO only
    iso_url: 'https://releases.ubuntu.com/24.04/ubuntu-24.04.1-live-server-amd64.iso',
    dest_folder: 'ubuntu-24.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd', iso: 'ubuntu-24.04-live-server-amd64.iso' },
    size: 'ISO only',
    iso_size: '~2.6 GB',
    supports_iso: true,
    iso_only: true,
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'casper',
      cmdline: 'boot=casper netboot=url url=http://${server_ip}:${port}/ubuntu-24.04/',
      requires_internet: false
    }
  },
  {
    id: 'ubuntu-22.04',
    name: 'Ubuntu 22.04 LTS (Jammy)',
    // No netboot images available for 22.04 - use ISO only
    iso_url: 'https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso',
    dest_folder: 'ubuntu-22.04',
    files: { kernel: 'vmlinuz', initrd: 'initrd', iso: 'ubuntu-22.04-live-server-amd64.iso' },
    size: 'ISO only',
    iso_size: '~2.4 GB',
    supports_iso: true,
    iso_only: true,
    menu_config: {
      entry_type: 'boot',
      boot_mode: 'casper',
      cmdline: 'boot=casper netboot=url url=http://${server_ip}:${port}/ubuntu-22.04/',
      requires_internet: false
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

// Kaspersky Rescue Disk with version selection
const KASPERSKY_CONFIG = {
  id: 'kaspersky',
  name: 'Kaspersky Rescue Disk',
  dest_folder: 'kaspersky',
  dynamic_versions: true
}

function AssetManager() {
  const [assets, setAssets] = useState({ http: [], tftp: [], ipxe: [] })
  const [catalog, setCatalog] = useState({ ubuntu: [], debian: [], windows: [], rescue: [] })
  const [merging, setMerging] = useState({})       // version_dir → true/false
  const [mergeStatus, setMergeStatus] = useState({}) // version_dir → step string
  const [downloading, setDownloading] = useState({})
  const [downloadStatus, setDownloadStatus] = useState({})
  const [downloadProgress, setDownloadProgress] = useState({}) // Track download progress percentages
  const [downloadIso, setDownloadIso] = useState({}) // Track ISO download option for each distro
  const [systemRescueVersions, setSystemRescueVersions] = useState([])
  const [selectedSysrescueVersion, setSelectedSysrescueVersion] = useState(null)
  const [kasperskyVersions, setKasperskyVersions] = useState([])
  const [selectedKasperskyVersion, setSelectedKasperskyVersion] = useState(null)
  const [uploadDest, setUploadDest] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const [uploading, setUploading] = useState(false)
  const uploadInputRef = useRef(null)

  const pollProgress = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/download/progress')
      const data = await response.json()
      if (data.downloads) {
        setDownloadProgress(data.downloads)

        const activeDownloads = {}
        const completedDownloads = {}
        Object.keys(data.downloads).forEach(key => {
          const status = data.downloads[key].status
          if (status === 'downloading' || status === 'extracting') {
            DOWNLOADABLE_DISTROS.forEach(distro => {
              if (key.includes(distro.dest_folder)) {
                activeDownloads[distro.id] = true
              }
            })
          } else if (status === 'extracted' || status === 'complete') {
            DOWNLOADABLE_DISTROS.forEach(distro => {
              if (key.includes(distro.dest_folder)) {
                completedDownloads[distro.id] = false
              }
            })
          }
        })

        if (Object.keys(activeDownloads).length > 0) {
          setDownloading(prev => ({ ...prev, ...activeDownloads }))
        }
        if (Object.keys(completedDownloads).length > 0) {
          setDownloading(prev => ({ ...prev, ...completedDownloads }))
        }
      }
    } catch (error) {
      console.error('Failed to fetch progress:', error)
    }
  }, [])

  useEffect(() => {
    fetchAssets()
    fetchCatalog()
    fetchSystemRescueVersions()
    fetchKasperskyVersions()
    pollProgress()

    const interval = setInterval(pollProgress, 2000)
    return () => clearInterval(interval)
  }, [pollProgress])

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

  const mergeSquashfs = async (versionDir) => {
    setMerging(prev => ({ ...prev, [versionDir]: true }))
    setMergeStatus(prev => ({ ...prev, [versionDir]: 'Starting…' }))
    try {
      await fetch(`/api/assets/merge-squashfs?version_dir=${encodeURIComponent(versionDir)}`, { method: 'POST' })
      // Poll for progress
      const poll = setInterval(async () => {
        try {
          const r = await fetch(`/api/assets/merge-progress?version_dir=${encodeURIComponent(versionDir)}`)
          const data = await r.json()
          setMergeStatus(prev => ({ ...prev, [versionDir]: data.step || '' }))
          if (data.status === 'done' || data.status === 'error') {
            clearInterval(poll)
            setMerging(prev => ({ ...prev, [versionDir]: false }))
            if (data.status === 'done') fetchCatalog()
          }
        } catch { clearInterval(poll) }
      }, 3000)
    } catch (e) {
      setMergeStatus(prev => ({ ...prev, [versionDir]: `Error: ${e.message}` }))
      setMerging(prev => ({ ...prev, [versionDir]: false }))
    }
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadStatus(`Uploading ${file.name}…`)
    const form = new FormData()
    form.append('file', file)
    if (uploadDest) form.append('dest', uploadDest)
    try {
      const resp = await fetch('/api/assets/upload', { method: 'POST', body: form })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Upload failed')
      setUploadStatus(`✅ Saved: ${data.saved}`)
      fetchAssets()
      fetchCatalog()
    } catch (err) {
      setUploadStatus(`❌ ${err.message}`)
    } finally {
      setUploading(false)
      e.target.value = ''
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

  const fetchKasperskyVersions = async () => {
    try {
      const response = await fetch('/api/assets/versions/kaspersky')
      const data = await response.json()
      setKasperskyVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedKasperskyVersion(data.versions[0]) // Select version 24 (recommended) by default
      }
    } catch (error) {
      console.error('Failed to fetch Kaspersky versions:', error)
    }
  }

  const downloadDistro = async (distro) => {
    setDownloading(prev => ({ ...prev, [distro.id]: true }))
    const includeIso = downloadIso[distro.id] || false

    try {
      // Download kernel + initrd in parallel (unless ISO-only)
      if (!distro.iso_only) {
        setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading kernel + initrd in parallel...' }))

        const kernelDest = `${distro.dest_folder}/${distro.files.kernel}`
        const initrdDest = `${distro.dest_folder}/${distro.files.initrd}`

        // Parallel download using Promise.all
        const [kernelResponse, initrdResponse] = await Promise.all([
          fetch('/api/assets/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              url: distro.kernel_url,
              dest: kernelDest
            })
          }),
          fetch('/api/assets/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              url: distro.initrd_url,
              dest: initrdDest
            })
          })
        ])

        // Check both responses
        if (!kernelResponse.ok) {
          const error = await kernelResponse.json()
          throw new Error(error.detail || 'Failed to download kernel')
        }

        if (!initrdResponse.ok) {
          const error = await initrdResponse.json()
          throw new Error(error.detail || 'Failed to download initrd')
        }
      }

      // Download ISO if requested (or if ISO-only distro)
      if (distro.iso_only || (distro.supports_iso && includeIso)) {
        setDownloadStatus(prev => ({ ...prev, [distro.id]: 'Downloading ISO... (this may take a while)' }))
        const isoDest = `${distro.dest_folder}/${distro.files.iso}`
        const isoUrl = distro.iso_url

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
      const isoDest = `rescue-${selectedSysrescueVersion.version}/${selectedSysrescueVersion.iso_name}`

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

  const downloadKaspersky = async () => {
    if (!selectedKasperskyVersion) return

    const distroId = 'kaspersky-' + selectedKasperskyVersion.version
    setDownloading(prev => ({ ...prev, [distroId]: true }))

    try {
      setDownloadStatus(prev => ({ ...prev, [distroId]: 'Downloading ISO... (this may take a while)' }))
      // Download to kaspersky-{version}/ folder to match backend scanning pattern
      const isoDest = `kaspersky-${selectedKasperskyVersion.version}/${selectedKasperskyVersion.iso_name}`

      const isoResponse = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: selectedKasperskyVersion.iso_url,
          dest: isoDest
        })
      })

      if (!isoResponse.ok) {
        const error = await isoResponse.json()
        throw new Error(error.detail || 'Failed to download ISO')
      }

      setDownloadStatus(prev => ({ ...prev, [distroId]: '✅ Downloaded and extracted!' }))

      setTimeout(() => {
        fetchCatalog()
        setDownloadStatus(prev => ({ ...prev, [distroId]: '' }))
      }, 3000)

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
          <button className="btn btn-secondary" onClick={() => { fetchAssets(); fetchCatalog() }}>
            🔄 Scan
          </button>
          <input
            type="text"
            className="form-control"
            style={{ width: '160px', fontSize: '13px' }}
            placeholder="subfolder (optional)"
            value={uploadDest}
            onChange={(e) => setUploadDest(e.target.value)}
            title="Destination subfolder inside /srv/http/ — leave empty for root"
          />
          <button
            className="btn btn-primary"
            onClick={() => uploadInputRef.current?.click()}
            disabled={uploading}
          >
            📁 Upload File
          </button>
          <input ref={uploadInputRef} type="file" style={{ display: 'none' }} onChange={handleUpload} />
        </div>
        {uploadStatus && (
          <div style={{ fontSize: '13px', marginTop: '6px', color: uploadStatus.startsWith('✅') ? 'var(--color-success)' : uploadStatus.startsWith('❌') ? 'var(--color-danger)' : 'var(--color-text-secondary)' }}>
            {uploadStatus}
          </div>
        )}
      </div>

      <div className="asset-content">
        {/* Discovered Distributions */}
        <section className="asset-section">
          <h3>📊 Discovered Distributions</h3>

          {/* Ubuntu */}
          {catalog.ubuntu && catalog.ubuntu.length > 0 && (
            <div className="distro-group">
              <h4>🐧 Ubuntu</h4>
              {catalog.ubuntu.map((dist, idx) => {
                const versionDir = `ubuntu-${dist.version}`
                const isMerging = merging[versionDir]
                const squashfsLabel = dist.squashfs
                  ? dist.squashfs.includes('merged') ? '✓ merged.squashfs ✅' : '⚠️ layered squashfs'
                  : null
                return (
                  <div key={idx} className="distro-item">
                    <div className="distro-info">
                      <div className="distro-name">✅ Ubuntu {dist.version}</div>
                      <div className="distro-files">
                        {dist.kernel && <span className="file-badge">✓ kernel</span>}
                        {dist.initrd && <span className="file-badge">✓ initrd</span>}
                        {dist.iso && <span className="file-badge">✓ ISO</span>}
                        {squashfsLabel && <span className="file-badge">{squashfsLabel}</span>}
                      </div>
                      {isMerging && (
                        <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                          ⏳ {mergeStatus[versionDir]}
                        </div>
                      )}
                      {!isMerging && mergeStatus[versionDir] && !dist.needs_merge && (
                        <div style={{ fontSize: '12px', color: 'var(--color-success)', marginTop: '4px' }}>
                          ✅ {mergeStatus[versionDir]}
                        </div>
                      )}
                    </div>
                    <div className="distro-actions">
                      {dist.needs_merge && (
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => mergeSquashfs(versionDir)}
                          disabled={isMerging}
                          title="Merge squashfs layers into one file — enables fast HTTP boot without NFS or full ISO in RAM"
                        >
                          {isMerging ? '⏳ Merging…' : '🔀 Merge layers'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
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
                  <div className="distro-actions"></div>
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

                  {/* Progress bars for active downloads */}
                  {downloading[distro.id] && (
                    <div style={{ marginTop: '8px' }}>
                      {/* Kernel progress */}
                      {downloadProgress[`${distro.dest_folder}/vmlinuz`] && (
                        <div style={{ marginBottom: '8px' }}>
                          <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>Kernel</div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                            <span>{downloadProgress[`${distro.dest_folder}/vmlinuz`].percentage}%</span>
                            <span>{(downloadProgress[`${distro.dest_folder}/vmlinuz`].downloaded / 1024 / 1024).toFixed(1)} MB / {(downloadProgress[`${distro.dest_folder}/vmlinuz`].total / 1024 / 1024).toFixed(1)} MB</span>
                          </div>
                          <div style={{ width: '100%', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${downloadProgress[`${distro.dest_folder}/vmlinuz`].percentage}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 0.3s' }}></div>
                          </div>
                        </div>
                      )}

                      {/* Initrd progress */}
                      {downloadProgress[`${distro.dest_folder}/initrd`] && (
                        <div style={{ marginBottom: '8px' }}>
                          <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>Initrd</div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                            <span>{downloadProgress[`${distro.dest_folder}/initrd`].percentage}%</span>
                            <span>{(downloadProgress[`${distro.dest_folder}/initrd`].downloaded / 1024 / 1024).toFixed(1)} MB / {(downloadProgress[`${distro.dest_folder}/initrd`].total / 1024 / 1024).toFixed(1)} MB</span>
                          </div>
                          <div style={{ width: '100%', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${downloadProgress[`${distro.dest_folder}/initrd`].percentage}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 0.3s' }}></div>
                          </div>
                        </div>
                      )}

                      {/* ISO progress */}
                      {distro.supports_iso && distro.files.iso && downloadProgress[`${distro.dest_folder}/${distro.files.iso}`] && (
                        <div style={{ marginBottom: '8px' }}>
                          <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>
                            ISO
                            {downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].status === 'extracting' &&
                              <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>(Extracting...)</span>
                            }
                            {downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].status === 'extracted' &&
                              <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>
                                ✓ Extracted ({downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].file_count} files)
                              </span>
                            }
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                            <span>{downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].percentage}%</span>
                            <span>{(downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].downloaded / 1024 / 1024).toFixed(0)} MB / {(downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].total / 1024 / 1024).toFixed(0)} MB</span>
                          </div>
                          <div style={{ width: '100%', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].percentage}%`, height: '100%', background: 'var(--color-success)', transition: 'width 0.3s' }}></div>
                          </div>
                        </div>
                      )}
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
                        <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>
                          SystemRescue ISO
                          {downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].status === 'extracting' &&
                            <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>(Extracting...)</span>
                          }
                          {downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].status === 'extracted' &&
                            <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>
                              ✓ Extracted ({downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].file_count} files)
                            </span>
                          }
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                          <span>{downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].percentage}%</span>
                          <span>
                            {(downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].downloaded / 1024 / 1024 / 1024).toFixed(2)} GB /
                            {(downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].total / 1024 / 1024 / 1024).toFixed(2)} GB
                          </span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${downloadProgress[`${SYSTEMRESCUE_CONFIG.dest_folder}/${selectedSysrescueVersion?.iso_name}`].percentage}%`, height: '100%', background: 'var(--color-success)', transition: 'width 0.3s' }}></div>
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

            {/* Kaspersky Rescue Disk Version Selector */}
            <div style={{ marginTop: '32px', paddingTop: '24px', borderTop: '1px solid var(--color-border)' }}>
              <h4>🛡️ Kaspersky Rescue Disk</h4>
              <p className="text-sm text-muted" style={{ marginBottom: '16px' }}>
                Select a version to download (ISO will need to be extracted)
              </p>
              {kasperskyVersions.length > 0 ? (
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
                      value={selectedKasperskyVersion?.version || ''}
                      onChange={(e) => {
                        const version = kasperskyVersions.find(v => v.version === e.target.value)
                        setSelectedKasperskyVersion(version)
                      }}
                    >
                      {kasperskyVersions.map(v => (
                        <option key={v.version} value={v.version}>
                          {v.name} ({v.size_est})
                        </option>
                      ))}
                    </select>
                    {selectedKasperskyVersion?.notes && (
                      <div style={{ fontSize: '11px', marginTop: '4px', color: 'var(--color-text-secondary)' }}>
                        ℹ️ {selectedKasperskyVersion.notes}
                      </div>
                    )}
                  </div>
                  <div style={{ minWidth: '300px' }}>
                    {/* Progress bar for Kaspersky */}
                    {downloading['kaspersky-' + selectedKasperskyVersion?.version] && downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`] && (
                      <div style={{ marginBottom: '8px' }}>
                        <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>
                          Kaspersky ISO
                          {downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].status === 'extracting' &&
                            <span style={{ marginLeft: '8px', color: 'var(--color-warning)' }}>(Extracting...)</span>
                          }
                          {downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].status === 'extracted' &&
                            <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>
                              ✓ Extracted ({downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].file_count} files)
                            </span>
                          }
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                          <span>{downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].percentage}%</span>
                          <span>
                            {(downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].downloaded / 1024 / 1024).toFixed(0)} MB /
                            {(downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].total / 1024 / 1024).toFixed(0)} MB
                          </span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`].percentage}%`, height: '100%', background: 'var(--color-warning)', transition: 'width 0.3s' }}></div>
                        </div>
                      </div>
                    )}

                    {downloadStatus['kaspersky-' + selectedKasperskyVersion?.version] && (
                      <div className="download-status" style={{ marginBottom: '8px' }}>
                        {downloadStatus['kaspersky-' + selectedKasperskyVersion?.version]}
                      </div>
                    )}
                    <button
                      className="btn btn-primary"
                      onClick={downloadKaspersky}
                      disabled={!selectedKasperskyVersion || downloading['kaspersky-' + selectedKasperskyVersion?.version]}
                    >
                      {downloading['kaspersky-' + selectedKasperskyVersion?.version] ? '⏳ Downloading...' : '⬇️ Download ISO'}
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
                {assets.http.map((file, idx) => (
                  <li key={idx} className="file-item">
                    <span className="file-icon">📄</span>
                    <span className="file-name">{file}</span>
                  </li>
                ))}
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
