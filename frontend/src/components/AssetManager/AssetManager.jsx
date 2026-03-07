import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import './AssetManager.css'

const ASSETS_UPLOAD_STATUS_KEY = 'assets_upload_status_v1'

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

function DownloadProgressBlock({
  title,
  progress,
  tone = 'primary',
  unit = 'GB',
  divisor = 1024 * 1024 * 1024,
  decimals = 2,
  showExtraction = false,
  extractingTone = 'success',
}) {
  if (!progress) return null
  const downloaded = ((progress.downloaded || 0) / divisor).toFixed(decimals)
  const total = ((progress.total || 0) / divisor).toFixed(decimals)

  return (
    <div className="dl-progress-block">
      <div className="dl-progress-title">
        {title}
        {showExtraction && progress.status === 'extracting' && (
          <span className={`dl-progress-stage dl-progress-stage-${extractingTone}`}>(Extracting...)</span>
        )}
        {showExtraction && progress.status === 'extracted' && (
          <span className="dl-progress-stage dl-progress-stage-success">
            ✓ Extracted ({progress.file_count || 0} files)
          </span>
        )}
      </div>
      <div className="dl-progress-meta">
        <span>{progress.percentage || 0}%</span>
        <span>{downloaded} {unit} / {total} {unit}</span>
      </div>
      <progress
        className={`dl-progress-meter dl-progress-meter-${tone}`}
        value={progress.percentage || 0}
        max="100"
      />
    </div>
  )
}

function UrlBadge({ url, urlStatus }) {
  const st = urlStatus[url]
  if (!st) return null
  if (st.checking) return <span className="url-badge url-badge-checking">🔍 Checking...</span>
  if (st.ok) {
    const gb = st.size ? ` · ${(st.size / 1024 / 1024 / 1024).toFixed(1)} GB` : ''
    return <span className="url-badge url-badge-ok">✅ Available{gb}</span>
  }
  return <span className="url-badge url-badge-error">❌ Not found — URL may be outdated</span>
}

function AssetManager() {
  const [_assets, setAssets] = useState({ http: [], tftp: [], ipxe: [] })
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
  const [uploadCategory, setUploadCategory] = useState('tools')
  const [uploadCategoryCustom, setUploadCategoryCustom] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const [uploading, setUploading] = useState(false)
  const uploadInputRef = useRef(null)
  const debianProductsRef = useRef([])
  const [urlStatus, setUrlStatus] = useState({}) // url → { checking, ok, size, error }
  const [nfsStatus, setNfsStatus] = useState(null) // null = not fetched yet
  const [pollInterval, setPollInterval] = useState(2000)
  const [presets, setPresets] = useState([])
  const [activeAcquirePresetId, setActiveAcquirePresetId] = useState('')
  const [showPresetManager, setShowPresetManager] = useState(false)
  const [newPresetName, setNewPresetName] = useState('')
  const [newPresetSection, setNewPresetSection] = useState('antivirus')
  const [presetStatus, setPresetStatus] = useState('')
  const [presetBusyId, setPresetBusyId] = useState('')
  const uploadStatusTone = uploadStatus.startsWith('✅')
    ? 'upload-status-success'
    : uploadStatus.startsWith('❌')
      ? 'upload-status-error'
      : 'upload-status-muted'

  const setPersistentUploadStatus = useCallback((value) => {
    setUploadStatus(value)
    try {
      if (!value) sessionStorage.removeItem(ASSETS_UPLOAD_STATUS_KEY)
      else sessionStorage.setItem(ASSETS_UPLOAD_STATUS_KEY, value)
    } catch {
      // Ignore storage errors
    }
  }, [])

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
    try {
      const saved = sessionStorage.getItem(ASSETS_UPLOAD_STATUS_KEY)
      if (saved) setUploadStatus(saved)
    } catch {
      // Ignore storage errors
    }
  }, [])

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

  const fetchPresets = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/presets')
      const data = await response.json()
      const next = Array.isArray(data.presets) ? data.presets : []
      setPresets(next)
    } catch (error) {
      console.error('Failed to fetch presets:', error)
      setPresets([])
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

  const createPreset = async () => {
    const name = newPresetName.trim()
    if (!name) return
    setPresetStatus('Creating preset...')
    try {
      const resp = await fetch('/api/assets/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          mode: 'acquire',
          section: newPresetSection,
          category: newPresetSection === 'antivirus' ? 'security' : 'custom',
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Failed to create preset')
      setNewPresetName('')
      setPresetStatus('✅ Preset created')
      await fetchPresets()
      setTimeout(() => setPresetStatus(''), 2000)
    } catch (error) {
      setPresetStatus(`❌ ${error.message}`)
      setTimeout(() => setPresetStatus(''), 3000)
    }
  }

  const toggleUserPreset = async (preset) => {
    setPresetBusyId(preset.id)
    try {
      const resp = await fetch(`/api/assets/presets/${preset.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !preset.enabled }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Failed to update preset')
      await fetchPresets()
    } catch (error) {
      setPresetStatus(`❌ ${error.message}`)
      setTimeout(() => setPresetStatus(''), 3000)
    } finally {
      setPresetBusyId('')
    }
  }

  const deleteUserPreset = async (preset) => {
    setPresetBusyId(preset.id)
    try {
      const resp = await fetch(`/api/assets/presets/${preset.id}`, { method: 'DELETE' })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Failed to delete preset')
      await fetchPresets()
    } catch (error) {
      setPresetStatus(`❌ ${error.message}`)
      setTimeout(() => setPresetStatus(''), 3000)
    } finally {
      setPresetBusyId('')
    }
  }


  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setPersistentUploadStatus(`Uploading ${file.name}…`)
    const form = new FormData()
    form.append('file', file)
    const categoryFolder = uploadCategory === 'new' ? uploadCategoryCustom.trim() : uploadCategory
    const effectiveDest = [categoryFolder, uploadDest.trim()].filter(Boolean).join('/')
    if (effectiveDest) form.append('dest', effectiveDest)
    try {
      const resp = await fetch('/api/assets/upload', { method: 'POST', body: form })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Upload failed')
      setPersistentUploadStatus(`✅ Saved: ${data.saved}`)
      fetchAssets()
      fetchCatalog()
    } catch (err) {
      setPersistentUploadStatus(`❌ ${err.message}`)
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

  useEffect(() => {
    fetchAssets()
    fetchCatalog()
    fetchUbuntuVersions()
    fetchUbuntuDesktopVersions()
    fetchDebianProducts()
    fetchPresets()
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
    fetchPresets,
    fetchKasperskyVersions,
    fetchNfsStatus,
    fetchSystemRescueVersions,
    fetchUbuntuDesktopVersions,
    fetchUbuntuVersions,
    pollProgress,
    pollInterval,
  ])

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
      setTimeout(() => {
        fetchCatalog()
        fetchNfsStatus()
        setDownloadStatus(prev => ({ ...prev, [distroId]: '' }))
      }, 2000)
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
      setTimeout(() => {
        fetchCatalog()
        fetchNfsStatus()
        setDownloadStatus(prev => ({ ...prev, [distroId]: '' }))
      }, 2000)
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
        fetchNfsStatus()
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
        fetchNfsStatus()
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
        fetchNfsStatus()
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

  const acquirePresets = useMemo(() => {
    return presets
      .filter(preset => preset.mode === 'acquire' && preset.enabled !== false && preset.section)
      .sort((a, b) => (a.order ?? 100) - (b.order ?? 100))
  }, [presets])

  useEffect(() => {
    if (!acquirePresets.length) {
      setActiveAcquirePresetId('')
      return
    }
    const isValid = acquirePresets.some(preset => preset.id === activeAcquirePresetId)
    if (!isValid) {
      setActiveAcquirePresetId(acquirePresets[0].id)
    }
  }, [acquirePresets, activeAcquirePresetId])

  const activeAcquireSection = useMemo(() => {
    if (!acquirePresets.length) return 'all'
    const selected = acquirePresets.find(preset => preset.id === activeAcquirePresetId)
    return selected?.section || 'all'
  }, [acquirePresets, activeAcquirePresetId])

  const installedSystemRescueVersions = useMemo(() => {
    const rows = Array.isArray(catalog.rescue) ? catalog.rescue : []
    return new Set(rows.map(row => String(row.version)))
  }, [catalog.rescue])

  const installedKasperskyVersions = useMemo(() => {
    const rows = Array.isArray(catalog.kaspersky) ? catalog.kaspersky : []
    return new Set(rows.map(row => String(row.version)))
  }, [catalog.kaspersky])

  return (
    <div className="asset-manager">
      <div className="asset-header">
        <h2>Asset Manager</h2>
        <div className="asset-actions">
          <button className="btn btn-secondary" onClick={() => { fetchAssets(); fetchCatalog(); fetchNfsStatus() }}>
            🔄 Scan
          </button>
          <select
            className="form-control upload-category-select"
            value={uploadCategory}
            onChange={(e) => setUploadCategory(e.target.value)}
            title="Top-level category folder inside /srv/http/"
          >
            <option value="tools">tools</option>
            <option value="antivirus">antivirus</option>
            <option value="new">new category…</option>
          </select>
          {uploadCategory === 'new' && (
            <input
              type="text"
              className="form-control upload-category-custom-input"
              placeholder="new category name"
              value={uploadCategoryCustom}
              onChange={(e) => setUploadCategoryCustom(e.target.value)}
              title="New top-level folder name inside /srv/http/"
            />
          )}
          <input
            type="text"
            className="form-control upload-dest-input"
            placeholder="subfolder (optional)"
            value={uploadDest}
            onChange={(e) => setUploadDest(e.target.value)}
            title="Optional subfolder under chosen category"
          />
          <button
            className="btn btn-primary"
            onClick={() => uploadInputRef.current?.click()}
            disabled={uploading}
          >
            📁 Upload File
          </button>
          <input ref={uploadInputRef} type="file" className="visually-hidden" onChange={handleUpload} />
        </div>
        {uploadStatus && (
          <div className={`upload-status ${uploadStatusTone}`}>
            {uploadStatus}
          </div>
        )}
      </div>

      <div className="asset-content">
        <div className="acquire-tabs">
          {acquirePresets.length > 0 ? (
            acquirePresets.map((preset) => (
              <button
                key={preset.id}
                className={`acquire-tab-btn ${activeAcquirePresetId === preset.id ? 'is-active' : ''}`}
                onClick={() => setActiveAcquirePresetId(preset.id)}
              >
                {preset.name}
              </button>
            ))
          ) : (
            <p className="text-sm text-muted">No presets found</p>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setShowPresetManager(prev => !prev)}
          >
            {showPresetManager ? 'Hide Preset Manager' : 'Manage Presets'}
          </button>
        </div>
        {showPresetManager && (
          <section className="asset-section preset-manager">
            <h3>Preset Manager</h3>
            <div className="preset-create-row">
              <input
                type="text"
                className="form-control"
                placeholder="New preset name"
                value={newPresetName}
                onChange={(e) => setNewPresetName(e.target.value)}
              />
              <select
                className="form-control"
                value={newPresetSection}
                onChange={(e) => setNewPresetSection(e.target.value)}
              >
                <option value="ubuntu">Ubuntu</option>
                <option value="debian">Debian</option>
                <option value="tools">Tools</option>
                <option value="antivirus">Antivirus</option>
              </select>
              <button className="btn btn-primary btn-sm" onClick={createPreset}>
                Add
              </button>
            </div>
            {presetStatus && <div className="upload-status">{presetStatus}</div>}
            <div className="preset-list">
              {presets
                .filter((preset) => preset.mode === 'acquire')
                .sort((a, b) => (a.order ?? 100) - (b.order ?? 100))
                .map((preset) => (
                  <div key={preset.id} className="preset-item">
                    <div className="preset-item-name">
                      {preset.name} <span className="text-sm text-muted">({preset.section})</span>
                    </div>
                    <div className="preset-item-actions">
                      {preset.source === 'user' ? (
                        <>
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={presetBusyId === preset.id}
                            onClick={() => toggleUserPreset(preset)}
                          >
                            {preset.enabled ? 'Disable' : 'Enable'}
                          </button>
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={presetBusyId === preset.id}
                            onClick={() => deleteUserPreset(preset)}
                          >
                            Delete
                          </button>
                        </>
                      ) : (
                        <span className="text-sm text-muted">System preset</span>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          </section>
        )}
        {/* ── Ubuntu ── */}
        {(activeAcquireSection === 'all' || activeAcquireSection === 'ubuntu') && (
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
                      onClick={downloadUbuntu}
                      disabled={!selectedUbuntuVersion || downloading['ubuntu-' + selectedUbuntuVersion?.version]}
                    >
                      {downloading['ubuntu-' + selectedUbuntuVersion?.version] ? '⏳ Downloading...' : '⬇️ Download ISO'}
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
                      onClick={downloadUbuntuDesktop}
                      disabled={!selectedUbuntuDesktopVersion || downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version]}
                    >
                      {downloading['ubuntu-desktop-' + selectedUbuntuDesktopVersion?.version] ? '⏳ Downloading...' : '⬇️ Download ISO'}
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
        )}

        {/* ── Debian ── */}
        {(activeAcquireSection === 'all' || activeAcquireSection === 'debian') && (
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
          </div>
        </section>
        )}

        {/* ── Tools ── */}
        {(activeAcquireSection === 'all' || activeAcquireSection === 'tools') && (
        <section className="asset-section">
          <h3>🛠️ Tools</h3>

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
          <div className="download-subsection download-subsection-last">
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
                      onClick={downloadSystemRescue}
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

        </section>
        )}

        {(activeAcquireSection === 'all' || activeAcquireSection === 'antivirus') && (
        <section className="asset-section">
          <h3>🛡️ Antivirus</h3>

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
          <div className="download-subsection download-subsection-last">
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
                    onClick={downloadKaspersky}
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
        </section>
        )}

      </div>
    </div>
  )
}

export default AssetManager
