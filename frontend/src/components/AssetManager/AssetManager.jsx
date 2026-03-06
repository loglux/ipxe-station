import { useState, useEffect, useCallback, useRef } from 'react'
import './AssetManager.css'

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

function UrlBadge({ url, urlStatus }) {
  const st = urlStatus[url]
  if (!st) return null
  if (st.checking) return <span style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>🔍 Checking...</span>
  if (st.ok) {
    const gb = st.size ? ` · ${(st.size / 1024 / 1024 / 1024).toFixed(1)} GB` : ''
    return <span style={{ fontSize: '11px', color: 'var(--color-success)' }}>✅ Available{gb}</span>
  }
  return <span style={{ fontSize: '11px', color: 'var(--color-danger)' }}>❌ Not found — URL may be outdated</span>
}

function AssetManager() {
  const [assets, setAssets] = useState({ http: [], tftp: [], ipxe: [] })
  const [catalog, setCatalog] = useState({ ubuntu: [], debian: [], windows: [], rescue: [] })
  const [downloading, setDownloading] = useState({})
  const [downloadStatus, setDownloadStatus] = useState({})
  const [downloadProgress, setDownloadProgress] = useState({}) // Track download progress percentages
  const [systemRescueVersions, setSystemRescueVersions] = useState([])
  const [selectedSysrescueVersion, setSelectedSysrescueVersion] = useState(null)
  const [kasperskyVersions, setKasperskyVersions] = useState([])
  const [selectedKasperskyVersion, setSelectedKasperskyVersion] = useState(null)
  const [debianProducts, setDebianProducts] = useState([])
  const [ubuntuVersions, setUbuntuVersions] = useState([])
  const [selectedUbuntuVersion, setSelectedUbuntuVersion] = useState(null)
  const [ubuntuLoading, setUbuntuLoading] = useState(false)
  const [ubuntuDesktopVersions, setUbuntuDesktopVersions] = useState([])
  const [selectedUbuntuDesktopVersion, setSelectedUbuntuDesktopVersion] = useState(null)
  const [ubuntuDesktopLoading, setUbuntuDesktopLoading] = useState(false)
  const [uploadDest, setUploadDest] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const [uploading, setUploading] = useState(false)
  const uploadInputRef = useRef(null)
  const debianProductsRef = useRef([])
  const [urlStatus, setUrlStatus] = useState({}) // url → { checking, ok, size, error }
  const [nfsStatus, setNfsStatus] = useState(null) // null = not fetched yet
  const [pollInterval, setPollInterval] = useState(2000)

  const checkUrl = useCallback(async (url) => {
    if (!url) return
    setUrlStatus(prev => ({ ...prev, [url]: { checking: true } }))
    try {
      const r = await fetch(`/api/assets/check-url?url=${encodeURIComponent(url)}`)
      const data = await r.json()
      setUrlStatus(prev => ({ ...prev, [url]: { checking: false, ...data } }))
    } catch {
      setUrlStatus(prev => ({ ...prev, [url]: { checking: false, ok: false, error: 'Network error' } }))
    }
  }, [])

  const pollProgress = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/download/progress')
      const data = await response.json()
      if (data.downloads) {
        setDownloadProgress(data.downloads)

        const activeDownloads = {}
        const completedDownloads = {}
        const currentDebianProducts = debianProductsRef.current
        Object.keys(data.downloads).forEach(key => {
          const status = data.downloads[key].status
          if (status === 'downloading' || status === 'extracting') {
            currentDebianProducts.forEach(distro => {
              if (key.includes(distro.dest_folder)) {
                activeDownloads[distro.id] = true
              }
            })
          } else if (status === 'extracted' || status === 'complete') {
            currentDebianProducts.forEach(distro => {
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

  const fetchNfsStatus = useCallback(async () => {
    setNfsStatus(prev => ({ ...prev, loading: true }))
    try {
      const r = await fetch('/api/assets/nfs-status')
      const data = await r.json()
      setNfsStatus({ ...data, loading: false })
    } catch {
      setNfsStatus({ running: false, loading: false, error: 'Request failed' })
    }
  }, [])

  // Read poll_interval from settings once on mount
  useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(data => { if (data.poll_interval) setPollInterval(data.poll_interval) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchAssets()
    fetchCatalog()
    fetchUbuntuVersions()
    fetchUbuntuDesktopVersions()
    fetchDebianProducts()
    fetchSystemRescueVersions()
    fetchKasperskyVersions()
    fetchNfsStatus()
    pollProgress()

    const interval = setInterval(pollProgress, pollInterval)
    return () => clearInterval(interval)
  }, [
    fetchAssets,
    fetchCatalog,
    fetchDebianProducts,
    fetchKasperskyVersions,
    fetchNfsStatus,
    fetchSystemRescueVersions,
    fetchUbuntuDesktopVersions,
    fetchUbuntuVersions,
    pollProgress,
    pollInterval,
  ])

  const fetchAssets = useCallback(async () => {
    try {
      const response = await fetch('/api/assets')
      const data = await response.json()
      setAssets(data)
    } catch (error) {
      console.error('Failed to fetch assets:', error)
    }
  }, [])

  const fetchCatalog = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/catalog')
      const data = await response.json()
      setCatalog(data)
    } catch (error) {
      console.error('Failed to fetch catalog:', error)
    }
  }, [])

  const fetchDebianProducts = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/versions/debian')
      const data = await response.json()
      const products = data.products || []
      setDebianProducts(products)
      debianProductsRef.current = products
      products.forEach((product) => {
        if (product.iso_url) checkUrl(product.iso_url)
      })
    } catch (error) {
      console.error('Failed to fetch Debian products:', error)
      setDebianProducts([])
      debianProductsRef.current = []
    }
  }, [checkUrl])


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

  const fetchSystemRescueVersions = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/versions/systemrescue')
      const data = await response.json()
      setSystemRescueVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedSysrescueVersion(data.versions[0])
        checkUrl(data.versions[0].iso_url)
      }
    } catch (error) {
      console.error('Failed to fetch SystemRescue versions:', error)
    }
  }, [checkUrl])

  const fetchKasperskyVersions = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/versions/kaspersky')
      const data = await response.json()
      setKasperskyVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedKasperskyVersion(data.versions[0])
        checkUrl(data.versions[0].iso_url)
      }
    } catch (error) {
      console.error('Failed to fetch Kaspersky versions:', error)
    }
  }, [checkUrl])

  const fetchUbuntuVersions = useCallback(async () => {
    setUbuntuLoading(true)
    try {
      const response = await fetch('/api/assets/versions/ubuntu')
      const data = await response.json()
      setUbuntuVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedUbuntuVersion(data.versions[0])
        checkUrl(data.versions[0].iso_url)
      }
    } catch (error) {
      console.error('Failed to fetch Ubuntu versions:', error)
    } finally {
      setUbuntuLoading(false)
    }
  }, [checkUrl])

  const fetchUbuntuDesktopVersions = useCallback(async () => {
    setUbuntuDesktopLoading(true)
    try {
      const response = await fetch('/api/assets/versions/ubuntu/desktop')
      const data = await response.json()
      setUbuntuDesktopVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedUbuntuDesktopVersion(data.versions[0])
        checkUrl(data.versions[0].iso_url)
      }
    } catch (error) {
      console.error('Failed to fetch Ubuntu Desktop versions:', error)
    } finally {
      setUbuntuDesktopLoading(false)
    }
  }, [checkUrl])

  const downloadUbuntuDesktop = async () => {
    if (!selectedUbuntuDesktopVersion) return
    const distroId = 'ubuntu-desktop-' + selectedUbuntuDesktopVersion.version
    setDownloading(prev => ({ ...prev, [distroId]: true }))
    try {
      setDownloadStatus(prev => ({ ...prev, [distroId]: 'Downloading ISO... (~5–6 GB, may take a while)' }))
      const isoDest = `${selectedUbuntuDesktopVersion.dest_folder}/${selectedUbuntuDesktopVersion.iso_name}`
      const resp = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: selectedUbuntuDesktopVersion.iso_url, dest: isoDest })
      })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Failed to download ISO')
      }
      setDownloadStatus(prev => ({ ...prev, [distroId]: '✅ Downloaded!' }))
      setTimeout(() => { fetchCatalog(); setDownloadStatus(prev => ({ ...prev, [distroId]: '' })) }, 2000)
    } catch (error) {
      setDownloadStatus(prev => ({ ...prev, [distroId]: `❌ Error: ${error.message}` }))
      setTimeout(() => setDownloadStatus(prev => ({ ...prev, [distroId]: '' })), 5000)
    } finally {
      setDownloading(prev => ({ ...prev, [distroId]: false }))
    }
  }

  const downloadUbuntu = async () => {
    if (!selectedUbuntuVersion) return
    const distroId = 'ubuntu-' + selectedUbuntuVersion.version
    setDownloading(prev => ({ ...prev, [distroId]: true }))
    try {
      setDownloadStatus(prev => ({ ...prev, [distroId]: 'Downloading ISO... (this may take a while)' }))
      const isoDest = `${selectedUbuntuVersion.dest_folder}/${selectedUbuntuVersion.iso_name}`
      const resp = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: selectedUbuntuVersion.iso_url, dest: isoDest })
      })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Failed to download ISO')
      }
      setDownloadStatus(prev => ({ ...prev, [distroId]: '✅ Downloaded!' }))
      setTimeout(() => { fetchCatalog(); setDownloadStatus(prev => ({ ...prev, [distroId]: '' })) }, 2000)
    } catch (error) {
      setDownloadStatus(prev => ({ ...prev, [distroId]: `❌ Error: ${error.message}` }))
      setTimeout(() => setDownloadStatus(prev => ({ ...prev, [distroId]: '' })), 5000)
    } finally {
      setDownloading(prev => ({ ...prev, [distroId]: false }))
    }
  }

  const downloadDistro = async (distro) => {
    setDownloading(prev => ({ ...prev, [distro.id]: true }))

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

      // Download ISO if this is an ISO-only distro
      if (distro.iso_only) {
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
        {/* ── Ubuntu ── */}
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
            <div className="distro-group" style={{ marginTop: '12px' }}>
              <h4>
                📡 NFS Boot
                <button
                  className="btn btn-sm btn-secondary"
                  style={{ marginLeft: '10px', fontSize: '11px', padding: '2px 8px' }}
                  onClick={fetchNfsStatus}
                  title="Refresh NFS status"
                >↻ Check</button>
              </h4>
              {!nfsStatus || nfsStatus.loading ? (
                <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>Checking NFS…</p>
              ) : !nfsStatus.running ? (
                <div style={{ fontSize: '13px' }}>
                  <span style={{ color: 'var(--color-danger)' }}>❌ NFS not running on host</span>
                  <span style={{ color: 'var(--color-text-secondary)', marginLeft: '10px' }}>
                    — needed for Ubuntu Server PXE boot
                  </span>
                  <div style={{ marginTop: '6px', color: 'var(--color-text-secondary)', fontFamily: 'monospace', fontSize: '12px' }}>
                    sudo bash scripts/setup-nfs.sh
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: '13px' }}>
                  <div style={{ marginBottom: '6px' }}>
                    <span style={{ color: 'var(--color-success)' }}>✅ NFS running</span>
                    {nfsStatus.exports?.length > 0 && (
                      <span style={{ color: 'var(--color-text-secondary)', marginLeft: '10px' }}>
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
                      <div key={dir} style={{ marginBottom: '8px', padding: '8px', background: 'var(--color-bg-secondary)', borderRadius: '6px' }}>
                        <div style={{ marginBottom: '4px' }}>
                          {covered
                            ? <span style={{ color: 'var(--color-success)' }}>✅ Ubuntu {dist.version} — export confirmed</span>
                            : cmdline
                              ? <span style={{ color: 'var(--color-warning)' }}>⚠️ Ubuntu {dist.version} — path from Settings, verify manually</span>
                              : <span style={{ color: 'var(--color-danger)' }}>❌ Ubuntu {dist.version} — set NFS Root Path in Settings first</span>
                          }
                        </div>
                        {cmdline ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <code style={{ fontSize: '11px', color: 'var(--color-text-secondary)', flex: 1, wordBreak: 'break-all' }}>
                              {cmdline}
                            </code>
                            <button
                              className="btn btn-sm btn-secondary"
                              style={{ flexShrink: 0, fontSize: '11px', padding: '2px 8px' }}
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
                          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
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
            <div style={{ marginBottom: '24px', paddingBottom: '24px', borderBottom: '1px solid var(--color-border)' }}>
              <h4 style={{ marginBottom: '8px' }}>Ubuntu Server (LTS)</h4>
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
                    <div style={{ marginTop: '4px' }}>
                      <UrlBadge url={selectedUbuntuVersion.iso_url} urlStatus={urlStatus} />
                    </div>
                  )}
                  {downloading['ubuntu-' + selectedUbuntuVersion?.version] &&
                    downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`] && (
                    <div className="download-picker-progress">
                      <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>Ubuntu ISO</div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                        <span>{downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`].percentage}%</span>
                        <span>
                          {(downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`].downloaded / 1024 / 1024 / 1024).toFixed(2)} GB /
                          {(downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`].total / 1024 / 1024 / 1024).toFixed(2)} GB
                        </span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ width: `${downloadProgress[`${selectedUbuntuVersion?.dest_folder}/${selectedUbuntuVersion?.iso_name}`].percentage}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 0.3s' }}></div>
                      </div>
                    </div>
                  )}
                  {downloadStatus['ubuntu-' + selectedUbuntuVersion?.version] && (
                    <div className="download-status download-picker-progress">
                      {downloadStatus['ubuntu-' + selectedUbuntuVersion?.version]}
                    </div>
                  )}
                  <div className="download-picker-actions">
                    <button
                      className="btn btn-primary"
                      onClick={downloadUbuntu}
                      disabled={!selectedUbuntuVersion || downloading['ubuntu-' + selectedUbuntuVersion?.version]}
                    >
                      {downloading['ubuntu-' + selectedUbuntuVersion?.version] ? '⏳ Downloading...' : '⬇️ Download ISO'}
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-muted" style={{ marginBottom: '8px' }}>Could not load versions from releases.ubuntu.com</p>
                  <button className="btn btn-secondary btn-sm" onClick={fetchUbuntuVersions}>🔄 Retry</button>
                </div>
              )}
            </div>
            {/* Ubuntu Desktop — dynamic version picker */}
            <div>
              <h4 style={{ marginBottom: '4px' }}>Ubuntu Desktop (LTS)</h4>
              <p className="text-sm text-muted" style={{ marginBottom: '8px' }}>
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
                    <div style={{ marginTop: '4px' }}>
                      <UrlBadge url={selectedUbuntuDesktopVersion.iso_url} urlStatus={urlStatus} />
                    </div>
                  )}
                  {downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version] &&
                    downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`] && (
                    <div className="download-picker-progress">
                      <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>
                        Ubuntu Desktop ISO
                        {downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].status === 'extracting' &&
                          <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>(Extracting...)</span>
                        }
                        {downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].status === 'extracted' &&
                          <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>
                            ✓ Extracted ({downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].file_count} files)
                          </span>
                        }
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                        <span>{downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].percentage}%</span>
                        <span>
                          {(downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].downloaded / 1024 / 1024 / 1024).toFixed(2)} GB /
                          {(downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].total / 1024 / 1024 / 1024).toFixed(2)} GB
                        </span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ width: `${downloadProgress[`${selectedUbuntuDesktopVersion?.dest_folder}/${selectedUbuntuDesktopVersion?.iso_name}`].percentage}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 0.3s' }}></div>
                      </div>
                    </div>
                  )}
                  {downloadStatus['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version] && (
                    <div className="download-status download-picker-progress">
                      {downloadStatus['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version]}
                    </div>
                  )}
                  <div className="download-picker-actions">
                    <button
                      className="btn btn-primary"
                      onClick={downloadUbuntuDesktop}
                      disabled={!selectedUbuntuDesktopVersion || downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version]}
                    >
                      {downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version] ? '⏳ Downloading...' : '⬇️ Download ISO'}
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-muted" style={{ marginBottom: '8px' }}>Could not load versions from releases.ubuntu.com</p>
                  <button className="btn btn-secondary btn-sm" onClick={fetchUbuntuDesktopVersions}>🔄 Retry</button>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ── Debian ── */}
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
            <p className="text-sm text-muted" style={{ marginBottom: '16px' }}>
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
                      <div style={{ marginBottom: '8px' }}>
                        <UrlBadge url={distro.iso_url} urlStatus={urlStatus} />
                      </div>
                    )}

                    {downloading[distro.id] && (
                      <div style={{ marginTop: '8px' }}>
                        {distro.files.kernel && downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`] && (
                          <div style={{ marginBottom: '8px' }}>
                            <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>linux</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                              <span>{downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`].percentage}%</span>
                              <span>
                                {(downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`].downloaded / 1024 / 1024).toFixed(1)} MB /
                                {(downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`].total / 1024 / 1024).toFixed(1)} MB
                              </span>
                            </div>
                            <div style={{ width: '100%', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                              <div style={{ width: `${downloadProgress[`${distro.dest_folder}/${distro.files.kernel}`].percentage}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 0.3s' }}></div>
                            </div>
                          </div>
                        )}

                        {distro.files.initrd && downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`] && (
                          <div style={{ marginBottom: '8px' }}>
                            <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>initrd.gz</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                              <span>{downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`].percentage}%</span>
                              <span>
                                {(downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`].downloaded / 1024 / 1024).toFixed(1)} MB /
                                {(downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`].total / 1024 / 1024).toFixed(1)} MB
                              </span>
                            </div>
                            <div style={{ width: '100%', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                              <div style={{ width: `${downloadProgress[`${distro.dest_folder}/${distro.files.initrd}`].percentage}%`, height: '100%', background: 'var(--color-primary)', transition: 'width 0.3s' }}></div>
                            </div>
                          </div>
                        )}

                        {distro.files.iso && downloadProgress[`${distro.dest_folder}/${distro.files.iso}`] && (
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
                              <span>
                                {(downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].downloaded / 1024 / 1024 / 1024).toFixed(2)} GB /
                                {(downloadProgress[`${distro.dest_folder}/${distro.files.iso}`].total / 1024 / 1024 / 1024).toFixed(2)} GB
                              </span>
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
                      title={distro.iso_only ? 'Download Debian ISO' : 'Download Debian installer files'}
                    >
                      {downloading[distro.id] ? '⏳ Downloading...' : distro.iso_only ? '⬇️ Download ISO' : '⬇️ Download Installer Files'}
                    </button>
                  </div>
                ))}
              </div>
          </div>
        </section>

        {/* ── Tools ── */}
        <section className="asset-section">
          <h3>🛠️ Tools</h3>

          {/* SystemRescue */}
          <div style={{ marginBottom: '24px', paddingBottom: '24px', borderBottom: '1px solid var(--color-border)' }}>
            <h4>🛟 SystemRescue</h4>
            <p className="text-sm text-muted" style={{ marginBottom: '16px' }}>
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
                    <div style={{ marginTop: '4px' }}>
                      <UrlBadge url={selectedSysrescueVersion.iso_url} urlStatus={urlStatus} />
                    </div>
                  )}
                  {downloading['systemrescue-' + selectedSysrescueVersion?.version] && downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`] && (
                    <div className="download-picker-progress">
                      <div style={{ fontSize: '11px', marginBottom: '2px', color: 'var(--color-text-secondary)' }}>
                        SystemRescue ISO
                        {downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].status === 'extracting' &&
                          <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>(Extracting...)</span>
                        }
                        {downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].status === 'extracted' &&
                          <span style={{ marginLeft: '8px', color: 'var(--color-success)' }}>
                            ✓ Extracted ({downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].file_count} files)
                          </span>
                        }
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                        <span>{downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].percentage}%</span>
                        <span>
                          {(downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].downloaded / 1024 / 1024 / 1024).toFixed(2)} GB /
                          {(downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].total / 1024 / 1024 / 1024).toFixed(2)} GB
                        </span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ width: `${downloadProgress[`rescue-${selectedSysrescueVersion?.version}/${selectedSysrescueVersion?.iso_name}`].percentage}%`, height: '100%', background: 'var(--color-success)', transition: 'width 0.3s' }}></div>
                      </div>
                    </div>
                  )}
                  {downloadStatus['systemrescue-' + selectedSysrescueVersion?.version] && (
                    <div className="download-status download-picker-progress">
                      {downloadStatus['systemrescue-' + selectedSysrescueVersion?.version]}
                    </div>
                  )}
                  <div className="download-picker-actions">
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

          {/* Kaspersky Rescue Disk */}
          <div>
            <h4>🛡️ Kaspersky Rescue Disk</h4>
            <p className="text-sm text-muted" style={{ marginBottom: '16px' }}>
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
                  <div style={{ fontSize: '11px', marginTop: '4px', color: 'var(--color-text-secondary)' }}>
                    ℹ️ {selectedKasperskyVersion.notes}
                  </div>
                )}
                {selectedKasperskyVersion?.iso_url && (
                  <div style={{ marginTop: '4px' }}>
                    <UrlBadge url={selectedKasperskyVersion.iso_url} urlStatus={urlStatus} />
                  </div>
                )}
                {downloading['kaspersky-' + selectedKasperskyVersion?.version] && downloadProgress[`kaspersky-${selectedKasperskyVersion?.version}/${selectedKasperskyVersion?.iso_name}`] && (
                  <div className="download-picker-progress">
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
                  <div className="download-status download-picker-progress">
                    {downloadStatus['kaspersky-' + selectedKasperskyVersion?.version]}
                  </div>
                )}
                <div className="download-picker-actions">
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
