import React, { useState, useEffect, useCallback } from 'react';
import './DHCPHelper.css';

const DHCPHelper = () => {
  const [serverTypes, setServerTypes] = useState([]);
  const [selectedType, setSelectedType] = useState('dnsmasq');
  const [pxeServerIP, setPxeServerIP] = useState('192.168.10.32');
  const [httpPort, setHttpPort] = useState(9021);
  const [tftpPort, setTftpPort] = useState(69);
  const [generatedConfig, setGeneratedConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [copySuccess, setCopySuccess] = useState(false);

  // Load server types and default IP from settings on mount
  useEffect(() => {
    fetch('/api/dhcp/server-types')
      .then(res => res.json())
      .then(data => setServerTypes(data.server_types))
      .catch(err => console.error('Failed to load server types:', err));

    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data.server_ip) setPxeServerIP(data.server_ip);
        if (data.http_port) setHttpPort(data.http_port);
      })
      .catch(() => {});
  }, []);

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

  // Auto-generate config when settings change
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

  return (
    <div className="dhcp-helper">
      <div className="dhcp-header">
        <h2>DHCP Configuration Helper</h2>
        <p className="dhcp-subtitle">
          Generate recommended DHCP settings for your PXE boot server
        </p>
      </div>

      <div className="dhcp-content">
        {/* Settings Panel */}
        <div className="dhcp-settings">
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
          <div className="config-output">
            <div className="config-header">
              <h3>Generated Configuration</h3>
              <div className="config-actions">
                <button onClick={copyToClipboard} className="btn-copy">
                  {copySuccess ? '✓ Copied!' : '📋 Copy'}
                </button>
                <button onClick={downloadConfig} className="btn-download">
                  💾 Download
                </button>
              </div>
            </div>

            <pre className="config-text">
              <code>{generatedConfig.config}</code>
            </pre>
          </div>
        )}

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
            {loading ? 'Checking...' : '🔍 Check Network DHCP'}
          </button>

          {validationResult && (
            <div className={`validation-result ${validationResult.status}`}>
              <h4>Validation Result:</h4>
              <p>{validationResult.message}</p>
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
            </div>
          )}
        </div>

        {/* Help Section */}
        <div className="dhcp-help">
          <h3>How to Use</h3>
          <ol>
            <li>Select your DHCP server type from the dropdown</li>
            <li>Verify the PXE Server IP matches your iPXE Station server</li>
            <li>Copy or download the generated configuration</li>
            <li>Add the configuration to your DHCP server config file</li>
            <li>Reload/restart your DHCP server</li>
            <li>Optionally, validate the network DHCP settings</li>
          </ol>

          <div className="help-note">
            <strong>Note:</strong> After applying these settings, PXE clients on your network
            will automatically boot from this iPXE Station server.
          </div>
        </div>
      </div>
    </div>
  );
};

export default DHCPHelper;
