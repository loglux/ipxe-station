import { useState, useEffect, useRef, useCallback } from 'react'
import './Monitoring.css'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

export default function Monitoring({ showSidebar = true, showServices = true }) {
  const [logs, setLogs] = useState([])
  const [clearLogsConfirmOpen, setClearLogsConfirmOpen] = useState(false)
  const [logType, setLogType] = useState('all')
  const [logLevel, setLogLevel] = useState('all')
  const [isPaused, setIsPaused] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [services, setServices] = useState({
    tftp: { status: 'unknown', uptime: 0 },
    http: { status: 'unknown', port: 9021 },
    rsyslog: { status: 'unknown' },
    proxy_dhcp: { status: 'unknown' }
  })
  const [metrics, setMetrics] = useState({
    disk_used: 0,
    disk_total: 0,
    active_connections: 0,
    total_requests: 0
  })
  const [bootSessions, setBootSessions] = useState([])
  const [pollInterval, setPollInterval] = useState(2000)
  const logsEndRef = useRef(null)

  const loadLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (logType !== 'all') params.append('type', logType)
      if (logLevel !== 'all') params.append('level', logLevel)
      params.append('limit', '100')

      const response = await fetch(`/api/monitoring/logs?${params}`)
      const data = await response.json()
      setLogs(data.logs || [])
    } catch (error) {
      console.error('Failed to load logs:', error)
    }
  }, [logLevel, logType])

  const loadServiceStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/monitoring/services')
      const data = await response.json()
      setServices(data.services || {})
    } catch (error) {
      console.error('Failed to load service status:', error)
    }
  }, [])

  const loadMetrics = useCallback(async () => {
    try {
      const response = await fetch('/api/monitoring/metrics')
      const data = await response.json()
      setMetrics(data.metrics || {})
    } catch (error) {
      console.error('Failed to load metrics:', error)
    }
  }, [])

  const loadBootSessions = useCallback(async () => {
    try {
      const response = await fetch('/api/monitoring/boot-sessions')
      const data = await response.json()
      setBootSessions(data.sessions || [])
    } catch (error) {
      console.error('Failed to load boot sessions:', error)
    }
  }, [])

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  // Read poll_interval from settings once on mount
  useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(data => { if (data.poll_interval) setPollInterval(data.poll_interval) })
      .catch(() => {})
  }, [])

  // Load initial logs and start polling
  useEffect(() => {
    const runLoad = () => {
      loadLogs()
      loadServiceStatus()
      loadMetrics()
      loadBootSessions()
    }

    const initialTimer = setTimeout(runLoad, 0)

    const interval = setInterval(() => {
      if (!isPaused) {
        runLoad()
      }
    }, pollInterval)

    return () => {
      clearTimeout(initialTimer)
      clearInterval(interval)
    }
  }, [isPaused, pollInterval, loadBootSessions, loadLogs, loadMetrics, loadServiceStatus])

  const formatAge = (seconds) => {
    if (seconds == null) return 'n/a'
    if (seconds < 1) return '<1s'
    if (seconds < 60) return `${Math.round(seconds)}s`
    return `${Math.round(seconds / 60)}m`
  }

  const getBootStatusClass = (status) => {
    if (status === 'stalled_after_ipxe' || status === 'suspected_loop') return 'boot-status-warning'
    if (status === 'boot_assets_requested' || status === 'boot_script_fetched' || status === 'beacon') {
      return 'boot-status-success'
    }
    return 'boot-status-neutral'
  }

  const clearLogs = async () => {
    try {
      await fetch('/api/monitoring/logs/clear', { method: 'POST' })
      setLogs([])
    } catch (error) {
      console.error('Failed to clear logs:', error)
    }
  }

  const downloadLogs = () => {
    const params = new URLSearchParams()
    if (logType !== 'all') params.append('type', logType)
    if (logLevel !== 'all') params.append('level', logLevel)
    params.append('limit', '1000')

    const a = document.createElement('a')
    a.href = `/api/monitoring/logs/download?${params.toString()}`
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const getLogLevelClass = (level) => {
    switch (level?.toLowerCase()) {
      case 'error': return 'log-error'
      case 'warning': return 'log-warning'
      case 'info': return 'log-info'
      default: return 'log-debug'
    }
  }

  const getServiceStatusIcon = (status) => {
    switch (status) {
      case 'running': return '✅'
      case 'stopped': return '❌'
      default: return '❓'
    }
  }

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  return (
    <div className="monitoring-container">
      {/* Left Panel - Logs */}
      <div className="monitoring-logs">
        <div className="logs-header">
          <h3>📋 System Logs</h3>
          <div className="logs-controls">
            <select
              value={logType}
              onChange={(e) => setLogType(e.target.value)}
              className="log-filter"
            >
              <option value="all">All Types</option>
              <option value="boot">Boot Flow</option>
              <option value="tftp">TFTP</option>
              <option value="http">HTTP</option>
              <option value="dhcp">DHCP</option>
              <option value="system">System</option>
              <option value="download">Downloads</option>
            </select>

            <select
              value={logLevel}
              onChange={(e) => setLogLevel(e.target.value)}
              className="log-filter"
            >
              <option value="all">All Levels</option>
              <option value="error">Errors</option>
              <option value="warning">Warnings</option>
              <option value="info">Info</option>
              <option value="debug">Debug</option>
            </select>

            <button
              className={`btn btn-sm ${isPaused ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setIsPaused(!isPaused)}
              title={isPaused ? 'Resume updates' : 'Pause updates'}
            >
              {isPaused ? '▶️ Resume' : '⏸️ Pause'}
            </button>

            <button
              className="btn btn-sm btn-secondary"
              onClick={downloadLogs}
              title="Download logs as text file"
            >
              💾 Download
            </button>

            <button
              className="btn btn-sm btn-danger"
              onClick={() => setClearLogsConfirmOpen(true)}
              title="Clear all logs"
            >
              🗑️ Clear
            </button>
          </div>
        </div>

        <div className="logs-content">
          {logs.length === 0 ? (
            <div className="logs-empty">
              <p>No logs to display</p>
              <small>Logs will appear here when system events occur</small>
            </div>
          ) : (
            <div className="logs-list">
              {logs.map((log, index) => (
                <div key={index} className={`log-entry ${getLogLevelClass(log.level)}`}>
                  <span className="log-timestamp">{log.timestamp}</span>
                  <span className="log-type">[{log.type}]</span>
                  <span className="log-level">[{log.level}]</span>
                  <span className="log-message">{log.message}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>

        <div className="logs-footer">
          <label className="auto-scroll-toggle">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            <span>Auto-scroll to bottom</span>
          </label>
          <span className="logs-count">{logs.length} entries</span>
        </div>
      </div>

      {showSidebar && (
        <div className="monitoring-sidebar">
          {showServices && (
          <div className="status-section">
            <h3>🔧 Services</h3>
            <div className="service-list">
              <div className="service-item">
                <span className="service-icon">{getServiceStatusIcon(services.tftp?.status)}</span>
                <div className="service-info">
                  <strong>TFTP Server</strong>
                  <small>{services.tftp?.status || 'unknown'}</small>
                </div>
              </div>
              <div className="service-item">
                <span className="service-icon">{getServiceStatusIcon(services.http?.status)}</span>
                <div className="service-info">
                  <strong>HTTP Server</strong>
                  <small>Port {services.http?.port || 9021}</small>
                </div>
              </div>
              <div className="service-item">
                <span className="service-icon">{getServiceStatusIcon(services.rsyslog?.status)}</span>
                <div className="service-info">
                  <strong>Rsyslog</strong>
                  <small>{services.rsyslog?.status || 'unknown'}</small>
                </div>
              </div>
              <div className="service-item">
                <span className="service-icon">{getServiceStatusIcon(services.proxy_dhcp?.status)}</span>
                <div className="service-info">
                  <strong>Proxy DHCP</strong>
                  <small>{services.proxy_dhcp?.status || 'unknown'}</small>
                </div>
              </div>
            </div>
          </div>
          )}

        {/* Metrics */}
        <div className="status-section">
          <h3>📊 Metrics</h3>
          <div className="metrics-list">
            <div className="metric-item">
              <span className="metric-label">Disk Usage</span>
              <span className="metric-value">
                {formatBytes(metrics.disk_used)} / {formatBytes(metrics.disk_total)}
              </span>
              <div className="metric-bar">
                <div
                  className="metric-bar-fill"
                  style={{ width: `${(metrics.disk_used / metrics.disk_total * 100) || 0}%` }}
                />
              </div>
            </div>

            <div className="metric-item">
              <span className="metric-label">Active Connections</span>
              <span className="metric-value">{metrics.active_connections || 0}</span>
            </div>

            <div className="metric-item">
              <span className="metric-label">Total Requests</span>
              <span className="metric-value">{metrics.total_requests || 0}</span>
            </div>
          </div>
        </div>

        <div className="status-section">
          <h3>🧭 Boot Sessions</h3>
          {bootSessions.length === 0 ? (
            <small className="text-muted">No PXE/iPXE client sessions yet</small>
          ) : (
            <div className="boot-sessions-list">
              {bootSessions.map((session) => (
                <div key={session.client_ip} className="boot-session-card">
                  <div className="boot-session-header">
                    <strong>{session.client_ip}</strong>
                    <span className={`boot-status-pill ${getBootStatusClass(session.status)}`}>
                      {session.status}
                    </span>
                  </div>
                  <div className="boot-session-meta">
                    <span>stage: {session.last_stage || 'unknown'}</span>
                    <span>seen: {formatAge(session.seconds_since_seen)} ago</span>
                  </div>
                  <div className="boot-session-counts">
                    <span>events {session.event_count || 0}</span>
                    <span>boot {session.boot_script_fetches || 0}</span>
                    <span>kernel {session.kernel_fetches || 0}</span>
                    <span>initrd {session.initrd_fetches || 0}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={clearLogsConfirmOpen}
        title="Clear all logs?"
        message="This will permanently remove all log entries and cannot be undone."
        confirmLabel="Clear"
        danger
        onConfirm={() => { setClearLogsConfirmOpen(false); clearLogs() }}
        onCancel={() => setClearLogsConfirmOpen(false)}
      />
    </div>
  )
}
