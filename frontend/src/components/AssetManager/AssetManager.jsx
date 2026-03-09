import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import './AssetManager.css'
import UbuntuSection from './UbuntuSection'
import DebianSection from './DebianSection'
import ToolsSection from './ToolsSection'

const ASSETS_UPLOAD_STATUS_KEY = 'assets_upload_status_v1'
const ASSETS_ACTIVE_PRESET_KEY = 'assets_active_preset_v1'
const ASSETS_UPLOAD_STATUS_TTL_MS = 60_000
const ASSETS_UPLOAD_SUCCESS_RESTORE_MS = 15_000
const ASSETS_UPLOAD_SUCCESS_HIDE_MS = 8_000
const ASSETS_UPLOAD_ERROR_HIDE_MS = 12_000

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
  const [assets, setAssets] = useState({ http: [], tftp: [], ipxe: [], asset_labels: {} })
  const [catalog, setCatalog] = useState({ ubuntu: [], debian: [], windows: [], rescue: [] })
  const [downloading, setDownloading] = useState({})
  const [downloadStatus, setDownloadStatus] = useState({})
  const [downloadProgress, setDownloadProgress] = useState({}) // Track download progress percentages
  const [systemRescueVersions, setSystemRescueVersions] = useState([])
  const [selectedSysrescueVersion, setSelectedSysrescueVersion] = useState(null)
  const [kasperskyVersions, setKasperskyVersions] = useState([])
  const [selectedKasperskyVersion, setSelectedKasperskyVersion] = useState(null)
  const [hirenVersions, setHirenVersions] = useState([])
  const [selectedHirenVersion, setSelectedHirenVersion] = useState(null)
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
  const [showUploadPanel, setShowUploadPanel] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)
  const [deletingAssetPath, setDeletingAssetPath] = useState('')
  const uploadStatusTimeoutRef = useRef(null)
  const uploadInputRef = useRef(null)
  const debianProductsRef = useRef([])
  const [urlStatus, setUrlStatus] = useState({}) // url → { checking, ok, size, error }
  const [nfsStatus, setNfsStatus] = useState(null) // null = not fetched yet
  const [pollInterval, setPollInterval] = useState(2000)
  const [presets, setPresets] = useState([])
  const [presetsLoaded, setPresetsLoaded] = useState(false)
  const [activeAcquirePresetId, setActiveAcquirePresetId] = useState(() => {
    try {
      return sessionStorage.getItem(ASSETS_ACTIVE_PRESET_KEY) || ''
    } catch {
      return ''
    }
  })
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

  const clearUploadStatus = useCallback(() => {
    if (uploadStatusTimeoutRef.current) {
      clearTimeout(uploadStatusTimeoutRef.current)
      uploadStatusTimeoutRef.current = null
    }
    setUploadStatus('')
    try {
      sessionStorage.removeItem(ASSETS_UPLOAD_STATUS_KEY)
    } catch {
      // Ignore storage errors
    }
  }, [])

  const setPersistentUploadStatus = useCallback((value, kind = 'info') => {
    setUploadStatus(value)
    try {
      if (!value) {
        sessionStorage.removeItem(ASSETS_UPLOAD_STATUS_KEY)
        return
      }
      sessionStorage.setItem(ASSETS_UPLOAD_STATUS_KEY, JSON.stringify({
        message: value,
        kind,
        ts: Date.now(),
      }))
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
      const raw = sessionStorage.getItem(ASSETS_UPLOAD_STATUS_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      const message = typeof saved?.message === 'string' ? saved.message : ''
      const kind = saved?.kind || 'info'
      const ts = Number(saved?.ts || 0)
      const age = Date.now() - ts
      const isExpired = !ts || age > ASSETS_UPLOAD_STATUS_TTL_MS
      const shouldDropSuccess = kind === 'success' && age > ASSETS_UPLOAD_SUCCESS_RESTORE_MS
      if (!message || isExpired || shouldDropSuccess) {
        sessionStorage.removeItem(ASSETS_UPLOAD_STATUS_KEY)
        return
      }
      setUploadStatus(message)
    } catch {
      // Clear legacy/plain-string stale format from older versions
      try {
        sessionStorage.removeItem(ASSETS_UPLOAD_STATUS_KEY)
      } catch {
        // Ignore storage errors
      }
    }
  }, [])

  useEffect(() => () => {
    if (uploadStatusTimeoutRef.current) {
      clearTimeout(uploadStatusTimeoutRef.current)
      uploadStatusTimeoutRef.current = null
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
    } finally {
      setPresetsLoaded(true)
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

  const uploadFileWithProgress = useCallback((formData, onProgress) => (
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/assets/upload')
      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percent: Math.round((event.loaded / event.total) * 100),
        })
      }
      xhr.onerror = () => reject(new Error('Upload failed'))
      xhr.onload = () => {
        let payload = {}
        try {
          payload = xhr.responseType === 'json' ? (xhr.response || {}) : JSON.parse(xhr.responseText || '{}')
        } catch {
          payload = {}
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload)
          return
        }
        reject(new Error(payload.detail || 'Upload failed'))
      }
      xhr.send(formData)
    })
  ), [])


  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setPersistentUploadStatus(`Uploading ${file.name}…`, 'progress')
    setUploadProgress({ loaded: 0, total: file.size || 0, percent: 0 })
    const form = new FormData()
    form.append('file', file)
    const effectiveDest = uploadDest.trim()
    if (effectiveDest) form.append('dest', effectiveDest)
    const categoryLabel = uploadCategory === 'new' ? uploadCategoryCustom.trim() || 'new' : uploadCategory
    if (categoryLabel) form.append('category', categoryLabel)
    try {
      const data = await uploadFileWithProgress(form, (progress) => {
        setUploadProgress(progress)
        setPersistentUploadStatus(`Uploading ${file.name}… ${progress.percent}%`, 'progress')
      })
      setPersistentUploadStatus(`✅ Saved: ${data.saved} (category: ${categoryLabel})`, 'success')
      if (uploadStatusTimeoutRef.current) clearTimeout(uploadStatusTimeoutRef.current)
      uploadStatusTimeoutRef.current = setTimeout(clearUploadStatus, ASSETS_UPLOAD_SUCCESS_HIDE_MS)
      fetchAssets()
      fetchCatalog()
    } catch (err) {
      setPersistentUploadStatus(`❌ ${err.message}`, 'error')
      if (uploadStatusTimeoutRef.current) clearTimeout(uploadStatusTimeoutRef.current)
      uploadStatusTimeoutRef.current = setTimeout(clearUploadStatus, ASSETS_UPLOAD_ERROR_HIDE_MS)
    } finally {
      setUploading(false)
      setUploadProgress(null)
      e.target.value = ''
    }
  }

  const deleteAssetPath = useCallback(async (path) => {
    if (!path) return
    const confirmed = window.confirm(`Delete resource file "${path}"?`)
    if (!confirmed) return

    setDeletingAssetPath(path)
    try {
      const resp = await fetch(`/api/assets/file?path=${encodeURIComponent(path)}`, {
        method: 'DELETE',
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        throw new Error(data.detail || 'Failed to delete resource')
      }
      setPersistentUploadStatus(`✅ Deleted: ${data.deleted || path}`, 'success')
      if (uploadStatusTimeoutRef.current) clearTimeout(uploadStatusTimeoutRef.current)
      uploadStatusTimeoutRef.current = setTimeout(clearUploadStatus, ASSETS_UPLOAD_SUCCESS_HIDE_MS)
      await fetchAssets()
      await fetchCatalog()
      await fetchNfsStatus()
    } catch (error) {
      setPersistentUploadStatus(`❌ ${error.message}`, 'error')
      if (uploadStatusTimeoutRef.current) clearTimeout(uploadStatusTimeoutRef.current)
      uploadStatusTimeoutRef.current = setTimeout(clearUploadStatus, ASSETS_UPLOAD_ERROR_HIDE_MS)
    } finally {
      setDeletingAssetPath('')
    }
  }, [clearUploadStatus, fetchAssets, fetchCatalog, fetchNfsStatus, setPersistentUploadStatus])

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

  const fetchHirenVersions = useCallback(async () => {
    try {
      const response = await fetch('/api/assets/versions/hiren')
      const data = await response.json()
      setHirenVersions(data.versions || [])
      if (data.versions && data.versions.length > 0) {
        setSelectedHirenVersion(data.versions[0])
        checkUrl(data.versions[0].iso_url)
      }
    } catch (error) {
      console.error('Failed to fetch Hiren versions:', error)
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
    fetchHirenVersions()
    fetchNfsStatus()
    pollProgress()

    const interval = setInterval(pollProgress, pollInterval)
    return () => clearInterval(interval)
  }, [
    fetchAssets,
    fetchCatalog,
    fetchDebianProducts,
    fetchHirenVersions,
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

  const downloadHiren = async () => {
    if (!selectedHirenVersion) return

    const distroId = 'hiren-' + selectedHirenVersion.version
    setDownloading(prev => ({ ...prev, [distroId]: true }))

    try {
      setDownloadStatus(prev => ({ ...prev, [distroId]: 'Downloading ISO... (this may take a while)' }))
      const baseFolder = selectedHirenVersion.dest_folder || `hiren-${selectedHirenVersion.version}`
      const isoDest = `${baseFolder}/${selectedHirenVersion.iso_name}`

      const isoResponse = await fetch('/api/assets/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: selectedHirenVersion.iso_url,
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

  const acquirePresets = useMemo(() => {
    return presets
      .filter(preset => preset.mode === 'acquire' && preset.enabled !== false && preset.section)
      .sort((a, b) => (a.order ?? 100) - (b.order ?? 100))
  }, [presets])

  const acquireTabs = useMemo(() => {
    const hasTools = acquirePresets.some((preset) => preset.section === 'tools')
    const hasAntivirus = acquirePresets.some((preset) => preset.section === 'antivirus')
    const toolsLike = acquirePresets.filter(
      (preset) => preset.section === 'tools' || preset.section === 'antivirus'
    )
    const toolsOrder = toolsLike.reduce((min, preset) => (
      Math.min(min, preset.order ?? 100)
    ), 100)

    const tabs = []
    acquirePresets.forEach((preset) => {
      if (preset.section === 'tools' || preset.section === 'antivirus') {
        if (!hasTools && !hasAntivirus) return
        if (tabs.some((tab) => tab.id === 'acquire_tools_rescue')) return
        tabs.push({
          id: 'acquire_tools_rescue',
          name: 'Tools & Rescue',
          section: 'tools_rescue',
          order: toolsOrder,
        })
        return
      }
      tabs.push({
        id: preset.id,
        name: preset.name,
        section: preset.section,
        order: preset.order ?? 100,
      })
    })
    return tabs.sort((a, b) => (a.order ?? 100) - (b.order ?? 100))
  }, [acquirePresets])

  useEffect(() => {
    // Do not clear saved tab during initial loading.
    if (!presetsLoaded || !acquireTabs.length) {
      return
    }
    const isValid = acquireTabs.some(tab => tab.id === activeAcquirePresetId)
    if (!isValid) {
      setActiveAcquirePresetId(acquireTabs[0].id)
    }
  }, [acquireTabs, activeAcquirePresetId, presetsLoaded])

  useEffect(() => {
    if (!presetsLoaded || !acquireTabs.length) return
    try {
      if (!activeAcquirePresetId) {
        sessionStorage.removeItem(ASSETS_ACTIVE_PRESET_KEY)
      } else {
        sessionStorage.setItem(ASSETS_ACTIVE_PRESET_KEY, activeAcquirePresetId)
      }
    } catch {
      // Ignore storage errors
    }
  }, [activeAcquirePresetId, acquireTabs.length, presetsLoaded])

  const activeAcquireSection = useMemo(() => {
    if (!acquireTabs.length) return 'all'
    const selected = acquireTabs.find(tab => tab.id === activeAcquirePresetId)
    return selected?.section || 'all'
  }, [acquireTabs, activeAcquirePresetId])

  const manualToolsRescueFiles = useMemo(() => {
    const files = Array.isArray(assets.http) ? assets.http : []
    const labels = assets?.asset_labels && typeof assets.asset_labels === 'object'
      ? assets.asset_labels
      : {}
    const prefixCategory = (path) => {
      if (path.startsWith('tools/')) return 'tools'
      if (path.startsWith('antivirus/')) return 'antivirus'
      if (path.startsWith('rescue/')) return 'rescue'
      return ''
    }
    const out = []
    const seen = new Set()
    files.forEach((path) => {
      const category = labels[path] || prefixCategory(path)
      if (!['tools', 'antivirus', 'rescue'].includes(category)) return
      if (seen.has(path)) return
      seen.add(path)
      out.push({ path, category })
    })
    return out
  }, [assets.http, assets.asset_labels])

  return (
    <div className="asset-manager">
      <div className="asset-header">
        <h2>Asset Manager</h2>
        <div className="asset-actions">
          <button className="btn btn-secondary" onClick={() => { fetchAssets(); fetchCatalog(); fetchNfsStatus() }}>
            🔄 Scan
          </button>
          <button
            className={`btn btn-secondary${showUploadPanel ? ' is-active' : ''}`}
            onClick={() => setShowUploadPanel(prev => !prev)}
          >
            📁 Upload File
          </button>
        </div>
      </div>

      {(showUploadPanel || uploading) && (
        <div className="upload-panel">
          <div className="upload-panel-fields">
            <select
              className="form-control upload-category-select"
              value={uploadCategory}
              onChange={(e) => setUploadCategory(e.target.value)}
              title="Category label only (does not change upload path)"
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
                title="Custom category label"
              />
            )}
            <input
              type="text"
              className="form-control upload-dest-input"
              placeholder="subfolder (optional)"
              value={uploadDest}
              onChange={(e) => setUploadDest(e.target.value)}
              title="Optional subfolder inside /srv/http/"
            />
            <button
              className="btn btn-primary"
              onClick={() => uploadInputRef.current?.click()}
              disabled={uploading}
            >
              Choose & Upload
            </button>
            <input ref={uploadInputRef} type="file" className="visually-hidden" onChange={handleUpload} />
          </div>
          {uploadStatus && (
            <div className={`upload-status ${uploadStatusTone}`}>
              {uploadStatus}
            </div>
          )}
          {uploading && uploadProgress && (
            <div className="upload-progress-wrap">
              <div className="upload-progress-meta">
                <span>{uploadProgress.percent}%</span>
                <span>{(uploadProgress.loaded / 1024 / 1024).toFixed(1)} MB / {(uploadProgress.total / 1024 / 1024).toFixed(1)} MB</span>
              </div>
              <progress className="upload-progress-meter" value={uploadProgress.percent} max="100" />
            </div>
          )}
        </div>
      )}

      <div className="asset-content">
        <div className="acquire-tabs">
          {acquireTabs.map((tab) => (
            <button
              key={tab.id}
              className={`acquire-tab-btn ${activeAcquirePresetId === tab.id ? 'is-active' : ''}`}
              onClick={() => setActiveAcquirePresetId(tab.id)}
            >
              {tab.name}
            </button>
          ))}
          <button
            className={`btn btn-secondary btn-sm${showPresetManager ? ' is-active' : ''}`}
            onClick={() => setShowPresetManager(prev => !prev)}
          >
            ⚙ Presets
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
        {/* No presets configured — show setup prompt instead of all sections */}
        {activeAcquireSection === 'all' && !acquireTabs.length && (
          <div className="empty-state" role="status">
            <p>No acquisition presets configured</p>
            <p className="text-sm text-muted">Open Presets to add Ubuntu, Debian, or Tools sections</p>
            <button className="btn btn-secondary btn-sm mt-md" onClick={() => setShowPresetManager(true)}>
              ⚙ Open Presets
            </button>
          </div>
        )}

        {/* ── Ubuntu ── */}
        {activeAcquireSection === 'ubuntu' && (
          <UbuntuSection
            catalog={catalog}
            nfsStatus={nfsStatus}
            fetchNfsStatus={fetchNfsStatus}
            ubuntuVersions={ubuntuVersions}
            selectedUbuntuVersion={selectedUbuntuVersion}
            setSelectedUbuntuVersion={setSelectedUbuntuVersion}
            ubuntuLoading={ubuntuLoading}
            fetchUbuntuVersions={fetchUbuntuVersions}
            ubuntuDesktopVersions={ubuntuDesktopVersions}
            selectedUbuntuDesktopVersion={selectedUbuntuDesktopVersion}
            setSelectedUbuntuDesktopVersion={setSelectedUbuntuDesktopVersion}
            ubuntuDesktopLoading={ubuntuDesktopLoading}
            fetchUbuntuDesktopVersions={fetchUbuntuDesktopVersions}
            downloading={downloading}
            downloadProgress={downloadProgress}
            downloadStatus={downloadStatus}
            checkUrl={checkUrl}
            urlStatus={urlStatus}
            onDownloadUbuntu={downloadUbuntu}
            onDownloadUbuntuDesktop={downloadUbuntuDesktop}
          />
        )}

        {/* ── Debian ── */}
        {activeAcquireSection === 'debian' && (
          <DebianSection
            catalog={catalog}
            debianProducts={debianProducts}
            downloading={downloading}
            downloadProgress={downloadProgress}
            downloadStatus={downloadStatus}
            urlStatus={urlStatus}
            onDownloadDistro={downloadDistro}
          />
        )}

        {/* ── Tools & Rescue ── */}
        {(activeAcquireSection === 'tools' || activeAcquireSection === 'antivirus' || activeAcquireSection === 'tools_rescue') && (
          <ToolsSection
            catalog={catalog}
            manualToolsRescueFiles={manualToolsRescueFiles}
            deletingAssetPath={deletingAssetPath}
            onDeleteAssetPath={deleteAssetPath}
            systemRescueVersions={systemRescueVersions}
            selectedSysrescueVersion={selectedSysrescueVersion}
            setSelectedSysrescueVersion={setSelectedSysrescueVersion}
            kasperskyVersions={kasperskyVersions}
            selectedKasperskyVersion={selectedKasperskyVersion}
            setSelectedKasperskyVersion={setSelectedKasperskyVersion}
            hirenVersions={hirenVersions}
            selectedHirenVersion={selectedHirenVersion}
            setSelectedHirenVersion={setSelectedHirenVersion}
            downloading={downloading}
            downloadProgress={downloadProgress}
            downloadStatus={downloadStatus}
            checkUrl={checkUrl}
            urlStatus={urlStatus}
            onDownloadSystemRescue={downloadSystemRescue}
            onDownloadKaspersky={downloadKaspersky}
            onDownloadHiren={downloadHiren}
          />
        )}

      </div>
    </div>
  )
}

export default AssetManager
