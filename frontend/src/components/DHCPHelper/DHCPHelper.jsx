import React, { useState, useEffect, useCallback, useRef } from 'react';
import './DHCPHelper.css';

const SCENARIO_ICONS = {
  proxy_ok: '✓', router_ok: '✓', conflict: '⚠',
  no_pxe: '✗', wrong_server: '⚠', proxy_no_dhcp: '✗', no_dhcp: '✗', partial: '⚠',
};

const SCENARIO_TITLES = {
  proxy_ok: 'Proxy DHCP active — correctly configured',
  router_ok: 'Router DHCP active — correctly configured',
  conflict: 'Conflict: proxy and router both responding',
  no_pxe: 'No PXE configuration found',
  wrong_server: 'PXE configured but pointing to wrong server',
  proxy_no_dhcp: 'Proxy DHCP active but no IP-assignment DHCP server',
  no_dhcp: 'No DHCP server found',
  partial: 'PXE partially configured',
};

const DHCPHelper = ({ settingsVersion = 0 }) => {
  // ── Active mode ───────────────────────────────────────────────────────────
  const [activeMode, setActiveMode] = useState('proxy'); // 'proxy' | 'router'

  // ── Proxy DHCP state ─────────────────────────────────────────────────────
  const [proxyStatus, setProxyStatus] = useState({ running: false, pid: null });
  const [proxySettings, setProxySettings] = useState({
    server_ip: '',
    http_port: 9021,
    support_bios: true,
    support_uefi: true,
  });
  const [proxyLoading, setProxyLoading] = useState(false);
  const [proxyMessage, setProxyMessage] = useState(null);
  const proxyPollRef = useRef(null);

  // ── Config generator state ───────────────────────────────────────────────
  const [serverTypes, setServerTypes] = useState([]);
  const [selectedType, setSelectedType] = useState('dnsmasq');
  const [pxeServerIP, setPxeServerIP] = useState('192.168.10.32');
  const [httpPort, setHttpPort] = useState(9021);
  const [tftpPort, setTftpPort] = useState(69);
  const [generatedConfig, setGeneratedConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [copySuccess, setCopySuccess] = useState(false);
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  // ── Proxy DHCP helpers ───────────────────────────────────────────────────

  const fetchProxyStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/proxy-dhcp/status');
      if (res.ok) {
        const data = await res.json();
        setProxyStatus({ running: data.running, pid: data.pid });
      }
    } catch {
      // silently ignore polling errors
    }
  }, []);

  const startProxyPolling = useCallback(() => {
    if (proxyPollRef.current) return;
    proxyPollRef.current = setInterval(fetchProxyStatus, 3000);
  }, [fetchProxyStatus]);

  const stopProxyPolling = useCallback(() => {
    if (proxyPollRef.current) {
      clearInterval(proxyPollRef.current);
      proxyPollRef.current = null;
    }
  }, []);

  const handleProxyStart = async () => {
    setProxyLoading(true);
    setProxyMessage(null);
    try {
      const res = await fetch('/api/proxy-dhcp/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(proxySettings),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setProxyStatus({ running: true, pid: data.pid });
        setProxyMessage({ type: 'success', text: `Started (pid ${data.pid})` });
      } else {
        setProxyMessage({ type: 'error', text: data.detail || data.error || 'Start failed' });
      }
    } catch (err) {
      setProxyMessage({ type: 'error', text: String(err) });
    } finally {
      setProxyLoading(false);
    }
  };

  const handleProxyStop = async () => {
    setProxyLoading(true);
    setProxyMessage(null);
    try {
      const res = await fetch('/api/proxy-dhcp/stop', { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.success) {
        setProxyStatus({ running: false, pid: null });
        setProxyMessage({ type: 'success', text: 'Stopped' });
      } else {
        setProxyMessage({ type: 'error', text: data.detail || data.error || 'Stop failed' });
      }
    } catch (err) {
      setProxyMessage({ type: 'error', text: String(err) });
    } finally {
      setProxyLoading(false);
    }
  };

  const handleProxySave = async () => {
    setProxyLoading(true);
    setProxyMessage(null);
    try {
      const res = await fetch('/api/proxy-dhcp/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(proxySettings),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setProxyStatus({ running: true, pid: data.pid });
        setProxyMessage({ type: 'success', text: `Applied — pid ${data.pid}` });
      } else {
        setProxyMessage({ type: 'error', text: data.detail || data.error || 'Apply failed' });
      }
    } catch (err) {
      setProxyMessage({ type: 'error', text: String(err) });
    } finally {
      setProxyLoading(false);
    }
  };

  // ── Mount: load everything ───────────────────────────────────────────────

  useEffect(() => {
    // Config generator setup
    fetch('/api/dhcp/server-types')
      .then(res => res.json())
      .then(data => setServerTypes(data.server_types))
      .catch(err => console.error('Failed to load server types:', err));

    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data.server_ip) {
          setPxeServerIP(data.server_ip);
          setProxySettings(prev => ({ ...prev, server_ip: data.server_ip }));
        }
        if (data.http_port) {
          setHttpPort(data.http_port);
          setProxySettings(prev => ({ ...prev, http_port: data.http_port }));
        }
      })
      .catch(() => {});

    // Proxy DHCP: load persisted config + initial status
    fetch('/api/proxy-dhcp/status')
      .then(res => res.json())
      .then(data => {
        setProxyStatus({ running: data.running, pid: data.pid });
        if (data.settings) {
          setProxySettings(prev => ({ ...prev, ...data.settings }));
        }
      })
      .catch(() => {});

    startProxyPolling();
    return () => stopProxyPolling();
  }, [startProxyPolling, stopProxyPolling, settingsVersion]);

  // ── Config generator helpers ─────────────────────────────────────────────

  const generateConfig = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/dhcp/config/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_type: selectedType,
          pxe_server_ip: pxeServerIP,
          http_port: parseInt(httpPort),
          tftp_port: parseInt(tftpPort)
        })
      });
      const data = await response.json();
      setGeneratedConfig(data);
    } catch (error) {
      console.error('Failed to generate config:', error);
    } finally {
      setLoading(false);
    }
  }, [httpPort, pxeServerIP, selectedType, tftpPort]);

  useEffect(() => {
    if (selectedType) {
      generateConfig();
    }
  }, [generateConfig, selectedType]);

  const copyToClipboard = () => {
    if (generatedConfig?.config) {
      navigator.clipboard.writeText(generatedConfig.config).then(() => {
        setCopySuccess(true);
        setTimeout(() => setCopySuccess(false), 2000);
      });
    }
  };

  const downloadConfig = () => {
    if (generatedConfig?.config) {
      const blob = new Blob([generatedConfig.config], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = generatedConfig.filename || 'dhcp-config.txt';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  const validateNetwork = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/dhcp/validate/network');
      const data = await response.json();
      setValidationResult(data);
    } catch (error) {
      console.error('Failed to validate network:', error);
      setValidationResult({
        status: 'error',
        message: 'Failed to connect to validation API'
      });
    } finally {
      setLoading(false);
    }
  };

  const applyFix = async (fix_url, fix_method = 'POST') => {
    setLoading(true);
    await fetch(fix_url, { method: fix_method });
    await validateNetwork();
  };

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="dhcp-helper">
      <div className="dhcp-header">
        <h2>DHCP Configuration Helper</h2>
        <p className="dhcp-subtitle">
          Generate recommended DHCP settings for your PXE boot server
        </p>
      </div>

      <div className="dhcp-content">

        {/* ── Mode toggle ───────────────────────────────────────────────── */}
        <div className="dhcp-mode-toggle">
          <button
            className={`dhcp-mode-btn${activeMode === 'proxy' ? ' active' : ''}`}
            onClick={() => setActiveMode('proxy')}
          >
            Proxy DHCP
            {proxyStatus.running && <span className="toggle-running-dot" />}
            <span className="badge-recommended">Recommended</span>
          </button>
          <button
            className={`dhcp-mode-btn${activeMode === 'router' ? ' active' : ''}`}
            onClick={() => setActiveMode('router')}
          >
            Router DHCP config
          </button>
        </div>

        {/* ── Option 1: Proxy DHCP ─────────────────────────────────────── */}
        {activeMode === 'proxy' && <div className="proxy-dhcp-panel">
          <div className="proxy-dhcp-title-row">
            <h3>Proxy DHCP Server</h3>
            <span className={`proxy-status-pill ${proxyStatus.running ? 'running' : 'stopped'}`}>
              {proxyStatus.running ? `Running (pid ${proxyStatus.pid})` : 'Stopped'}
            </span>
          </div>

          <p className="proxy-dhcp-description">
            Runs a lightweight dnsmasq instance alongside your existing DHCP server.
            Intercepts only PXE boot requests — no access to your router required.
          </p>

          <div className="proxy-dhcp-fields">
            <div className="setting-group">
              <label htmlFor="proxy-server-ip">Server IP:</label>
              <input
                id="proxy-server-ip"
                type="text"
                value={proxySettings.server_ip}
                onChange={e => setProxySettings(prev => ({ ...prev, server_ip: e.target.value }))}
                placeholder="192.168.1.1"
              />
            </div>

            <div className="setting-group">
              <label>Support:</label>
              <div className="proxy-checkboxes">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={proxySettings.support_bios}
                    onChange={e =>
                      setProxySettings(prev => ({ ...prev, support_bios: e.target.checked }))
                    }
                  />
                  BIOS (undionly.kpxe)
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={proxySettings.support_uefi}
                    onChange={e =>
                      setProxySettings(prev => ({ ...prev, support_uefi: e.target.checked }))
                    }
                  />
                  UEFI (ipxe.efi)
                </label>
              </div>
            </div>
          </div>

          <div className="proxy-dhcp-actions">
            {proxyStatus.running ? (
              <button
                onClick={handleProxyStop}
                disabled={proxyLoading}
                className="btn-proxy-stop"
              >
                {proxyLoading ? 'Stopping…' : 'Stop'}
              </button>
            ) : (
              <button
                onClick={handleProxyStart}
                disabled={proxyLoading}
                className="btn-proxy-start"
              >
                {proxyLoading ? 'Starting…' : 'Start'}
              </button>
            )}
            <button
              onClick={handleProxySave}
              disabled={proxyLoading}
              className="btn-proxy-apply"
            >
              {proxyLoading ? 'Applying…' : 'Save & Apply'}
            </button>
          </div>

          {proxyMessage && (
            <div className={`proxy-message ${proxyMessage.type}`}>
              {proxyMessage.text}
            </div>
          )}
        </div>}

        {/* ── Option 2: Configure your router ──────────────────────────── */}
        {activeMode === 'router' && <div className="proxy-dhcp-panel">
          <div className="proxy-dhcp-title-row">
            <h3>Configure your router's DHCP server</h3>
          </div>

          <p className="proxy-dhcp-description">
            If you have admin access to your DHCP server (router, ISC DHCP, MikroTik, Windows),
            add the PXE options directly to its config. Select your server type to generate
            the correct snippet.
          </p>

          <div className="dhcp-settings-inner">
            <div className="setting-group">
            <label htmlFor="server-type">DHCP Server Type:</label>
            <select
              id="server-type"
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
            >
              {serverTypes.map(type => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
            {serverTypes.find(t => t.id === selectedType)?.description && (
              <p className="setting-description">
                {serverTypes.find(t => t.id === selectedType).description}
              </p>
            )}
          </div>

          <div className="setting-group">
            <label htmlFor="pxe-ip">PXE Server IP:</label>
            <input
              id="pxe-ip"
              type="text"
              value={pxeServerIP}
              onChange={(e) => setPxeServerIP(e.target.value)}
              placeholder="192.168.10.32"
            />
          </div>

          <div className="setting-row">
            <div className="setting-group">
              <label htmlFor="http-port">HTTP Port:</label>
              <input
                id="http-port"
                type="number"
                value={httpPort}
                onChange={(e) => setHttpPort(e.target.value)}
                placeholder="9021"
              />
            </div>

            <div className="setting-group">
              <label htmlFor="tftp-port">TFTP Port:</label>
              <input
                id="tftp-port"
                type="number"
                value={tftpPort}
                onChange={(e) => setTftpPort(e.target.value)}
                placeholder="69"
              />
            </div>
          </div>
          </div>

          {/* Generated Config */}
          {generatedConfig && (
          <details className="config-output">
            <summary className="config-summary">
              <span>Generated Configuration</span>
              <div className="config-actions" onClick={e => e.stopPropagation()}>
                <button onClick={copyToClipboard} className="btn-copy">
                  {copySuccess ? '✓ Copied!' : '📋 Copy'}
                </button>
                <button onClick={downloadConfig} className="btn-download">
                  💾 Download
                </button>
              </div>
            </summary>

            <pre className="config-text">
              <code>{generatedConfig.config}</code>
            </pre>
          </details>
          )}
        </div>}

        {/* Network Validation */}
        <div className="dhcp-validation">
          <h3>Network DHCP Validation</h3>
          <p className="validation-description">
            Check if your network DHCP server has the correct PXE boot settings
          </p>

          <button
            onClick={validateNetwork}
            disabled={loading}
            className="btn-validate"
          >
            {loading ? '⏳ Probing BIOS / UEFI / iPXE…' : '🔍 Check Network DHCP'}
          </button>
          {loading && (
            <p className="validate-hint">
              Testing 3 client types sequentially — takes ~20–25 s on ASUS/dnsmasq routers.
            </p>
          )}

          {validationResult && (
            <div className={`validation-result ${validationResult.status}`}>

              {/* Scenario banner */}
              {validationResult.scenario && (
                <div className={`scenario-banner scenario-${validationResult.scenario}`}>
                  <span className="scenario-icon">{SCENARIO_ICONS[validationResult.scenario]}</span>
                  <strong>{SCENARIO_TITLES[validationResult.scenario]}</strong>
                </div>
              )}

              {/* Recommendations */}
              {validationResult.recommendations?.length > 0 && (
                <div className="recommendations">
                  {validationResult.recommendations.map((rec, i) => (
                    <div key={i} className={`recommendation recommendation-${rec.severity}`}>
                      <div className="recommendation-body">
                        <strong>{rec.title}</strong>
                        <p>{rec.description}</p>
                      </div>
                      {rec.fix_url && (
                        <button
                          className={`btn btn-sm btn-fix-${rec.severity}`}
                          onClick={() => applyFix(rec.fix_url, rec.fix_method)}
                          disabled={loading}
                        >
                          {rec.fix_label}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Collapsible probe table */}
              <details
                className="probe-details"
                onToggle={e => setDetailsExpanded(e.target.open)}
              >
                <summary>
                  Technical details ({Object.keys(validationResult.probes || {}).length} probes)
                </summary>
                {validationResult.probes && (
                  <table className="probe-table">
                    <thead>
                      <tr>
                        <th>Client type</th>
                        <th>Status</th>
                        <th>TFTP / Boot URL</th>
                        <th>Boot file</th>
                        <th>Offered IP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.values(validationResult.probes).map((probe) => (
                        <tr key={probe.label} className={`probe-row probe-${probe.status}`}>
                          <td>{probe.label}</td>
                          <td>
                            <span className={`probe-status-pill probe-status-${probe.status}`}>
                              {probe.status === 'success' ? '✓' : probe.status === 'no_response' ? '—' : probe.status === 'warning' ? '⚠' : '✗'}
                              {' '}{probe.status}
                            </span>
                          </td>
                          <td className="probe-mono">
                            {probe.boot_url || probe.tftp_server || <span className="text-muted">—</span>}
                          </td>
                          <td className="probe-mono">
                            {probe.bootfile || <span className="text-muted">—</span>}
                          </td>
                          <td className="probe-mono">
                            {probe.offered_ip || <span className="text-muted">—</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {validationResult.suggestions && (
                  <div className="validation-suggestions">
                    <h5>Suggestions:</h5>
                    <ul>
                      {validationResult.suggestions.map((suggestion, idx) => (
                        <li key={idx}>{suggestion}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </details>
            </div>
          )}
        </div>

        {/* Help Section */}
        <div className="dhcp-help">
          <h3>Which option to choose?</h3>
          <div className="help-options">
            <div className="help-option">
              <strong>Option 1 — Proxy DHCP</strong>
              <p>No router access needed. Start it here and it runs automatically.
                Best for most setups.</p>
            </div>
            <div className="help-option">
              <strong>Option 2 — Router config</strong>
              <p>You have shell/admin access to your DHCP server. Generate the snippet,
                paste it in, then reload the service.</p>
            </div>
          </div>
          <div className="help-note">
            Use <strong>Check Network DHCP</strong> above to confirm your chosen method
            is working correctly before booting a client.
          </div>
        </div>
      </div>
    </div>
  );
};

export default DHCPHelper;
