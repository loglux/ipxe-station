# API quick reference (for developers)

- `POST /api/ipxe/validate`: Body `IpxeMenuModel`. Returns `valid`, `errors`, `warnings`.
- `POST /api/ipxe/generate`: Body `IpxeMenuModel`. Returns `valid`, `message`, `warnings`, `script`.
- `GET /api/ipxe/templates`: Lists template names.
- `POST /api/ipxe/templates/{template_name}`: Returns template as JSON. Query params: `server_ip`, `port`.
- `POST /api/ipxe/menu/save`: Validates, lints, saves `boot.ipxe`. Returns `valid`, `message`, `warnings`, `script`, `config_path`.

Data roots: default `/srv/{http,ipxe,tftp}`; fallback to `/tmp/ipxe` if `/srv` is not writable. Override with `IPXE_DATA_ROOT`.
