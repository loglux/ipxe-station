# API quick reference (for developers)

## iPXE menu
- `POST /api/ipxe/validate`: Body `IpxeMenuModel`. Returns `valid`, `errors`, `warnings`.
- `POST /api/ipxe/generate`: Body `IpxeMenuModel`. Returns `valid`, `message`, `warnings`, `script`.
- `GET  /api/ipxe/templates`: Lists template names.
- `POST /api/ipxe/templates/{template_name}`: Returns template as JSON. Query params: `server_ip`, `port`.
- `POST /api/ipxe/menu/save`: Validates, lints, saves `boot.ipxe`. Returns `valid`, `message`, `warnings`, `script`, `config_path`.

## DHCP helper
- `POST /api/dhcp/config`: Body `DHCPConfig`. Returns generated dnsmasq/ISC config snippet.
- `GET  /api/dhcp/validate/network?expected_server_ip=<ip>`: Runs 3-probe DHCP validation (BIOS/UEFI64/iPXE).
  Returns `status`, `message`, `probes` dict with per-probe `{status, label, tftp_server, bootfile, offered_ip, boot_url}`.
  Takes ~25 s on ASUS routers (rate-limiting). Instant on ISC/pfSense/Mikrotik.

## Proxy DHCP (dnsmasq)
- `GET  /api/proxy-dhcp/status`: Returns `{running, pid, settings}`.
- `POST /api/proxy-dhcp/start`: Body `ProxyDHCPSettings`. Writes dnsmasq config, starts daemon.
- `POST /api/proxy-dhcp/stop`: Sends SIGTERM to dnsmasq, removes PID file.
- `GET  /api/proxy-dhcp/config`: Returns saved `ProxyDHCPSettings` as JSON.
- `POST /api/proxy-dhcp/config`: Body `ProxyDHCPSettings`. Saves settings without restarting.

  `ProxyDHCPSettings` fields: `server_ip`, `subnet` (auto-derived if blank), `http_port` (default 9021),
  `support_bios` (bool), `support_uefi` (bool).

## Settings
- `GET  /api/settings`: Returns current settings (`pxe_server_ip`, `http_port`, `tftp_port`, etc.).
- `POST /api/settings`: Saves settings.
- `GET  /api/network/detect`: Auto-detects server IP from active network interfaces.

## Data roots
Default `/srv/{http,ipxe,tftp}`; fallback to `/tmp/ipxe` if `/srv` is not writable.
Override with `IPXE_DATA_ROOT`. Settings and proxy-DHCP config persist under `/srv/`.
