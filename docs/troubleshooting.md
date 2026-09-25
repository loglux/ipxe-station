# Troubleshooting

Start at the symptom. Commands assume the server is at `SERVER` and you are on the host.

## The client never shows the iPXE menu

Typical sign: the machine skips the network and falls back to another device (some laptops open a
vendor recovery tool), or shows a message such as `PXE-E51` / `PXE-E53`. Note the message.

| Check | How |
|-------|-----|
| Link and cable (most common) | Look at the port lights; through a dock or adapter allow ~10 s for the link |
| Same network as the server | The client must be on the server's subnet and broadcast domain |
| UEFI network stack on | Without it a UEFI machine offers no "IPv4 network" boot entry; enable it in firmware setup |
| Right boot entry | Pick the **IPv4** network entry, not "HTTPS Boot" (see [Boot methods](boot-methods.md)) |
| Proxy DHCP running | `curl -s http://SERVER:9021/api/proxy-dhcp/status` → `"running":true` |
| Ports listening | `ss -ulnp \| grep -E ":(67\|69\|4011)\b"` |
| Firewall | `sudo ufw status`; UDP 67, 69 and 4011 and TCP 9021 must be reachable |
| Did the request arrive? | `docker logs --since 10m ipxe-station \| grep -v -E "GET /(status\|api)"` shows only the client's requests |

The **Monitoring** tab shows the same log plus service status. Successful `GET /api/*` polls of the UI
are not logged; boot-file requests (`/ipxe`, `/tftp`, `/http`) and errors are.

## The menu appears but an entry fails

- Kernel or initrd not found: **Save Menu** lints the entries and warns about files missing under
  `data/srv/http`. Check the asset in **Assets**.
- Ubuntu live hangs or reboots: HTTP ISO mode needs enough RAM (Server ≥ 4 GB, Desktop ≥ 8 GB); use
  NFS mode instead. Do not use `fetch=` with the squashfs on Ubuntu 22.04+.
- `autoexec.ipxe` broken (`#\!ipxe`): never write it from a shell heredoc (`!` gets escaped); use the
  **Boot Files** tab.
- The DHCP validator reports the iPXE probe as `not_configured`: a known false alarm, the actual boot
  works ([ROADMAP](../ROADMAP.md)).

## A Linux live entry says "NFS over TCP not available from ..."

Typical with Kaspersky Rescue Disk 24 (Debian live-boot), which mounts its files with `netboot=nfs`.
The message comes from the tiny NFS client inside the initrd and means it could not get the NFS port from
the server. **It does not mean your NFS server lacks TCP**: check with `rpcinfo -p SERVER` that NFS v3 over
TCP is registered (modern servers list only TCP, which is normal).

The usual cause is that **the network never came up inside the live system**. Confirm from the server:

- The Monitoring log (or `docker exec ipxe-station grep dnsmasq-dhcp /var/log/syslog`) shows the client's
  DHCP requests. If, after the client downloaded `vmlinuz` and `initrd`, no further DHCP request from its
  MAC appears, the live kernel never brought a NIC up.
- The NFS server's log has no mount request from the client (`journalctl -u nfs-mountd`).

Next steps: read the machine's NIC id from its `Client info` line and check that the live kernel knows
it (the kernel in the live image can be older than your hardware); try a USB Ethernet adapter (Realtek
r8152 and ASIX chips are widely supported); boot a rescue system with a newer kernel (SystemRescue) on
the same machine to tell a hardware-support problem from a server problem. live-boot also accepts
`ethdevice=eth0` and `ethdevice-timeout=60` if the link is slow to come up.

## WinPE booted but something is wrong

| Symptom | Likely cause and fix |
|---------|----------------------|
| Disk not visible in WinPE | SATA in "RAID On" (Intel RST/VMD): add the storage driver to the WIM (`DISM /Add-Driver`) or `drvload` it at runtime, then `echo rescan \| diskpart` and `Get-Disk` |
| No network address | Cable or adapter; USB Ethernet adapters need their driver inside the image |
| Your scripts fail to download | From the WinPE prompt: `ping SERVER`, then download `start.ps1` by hand (see the [example](../examples/winpe-provision/README.md#testing-without-repacking)) |
| Hangs while loading | The WIM is loaded into RAM; check available memory |
| Refused to start with Secure Boot on | The stock iPXE is unsigned: turn Secure Boot off (or see [ROADMAP](../ROADMAP.md) §8) |

Read-only commands that help inside WinPE:

```
wmic csproduct get vendor,name,version
wpeutil UpdateBootInfo
reg query HKLM\System\CurrentControlSet\Control /v PEFirmwareType
powershell -c "Confirm-SecureBootUEFI"
ipconfig
manage-bde -status
powershell -c "Get-Disk"
```

`wpeutil UpdateBootInfo` writes the boot mode into WinPE's RAM-only registry; `PEFirmwareType` is then
`0x2` for UEFI and `0x1` for BIOS. None of these commands change the machine. Do not run `diskpart`
`clean`, `format` or `convert` unless you mean to erase that disk.

## Changing firmware settings on a machine that has Windows

If BitLocker is on, changing Secure Boot, the boot order or the SATA mode can trigger a recovery-key
prompt. Suspend it in Windows first (`manage-bde -protectors -disable C: -RebootCount 1`) or have the
key ready. Switching SATA from "RAID On" to AHCI on an installed Windows makes it unbootable
(`INACCESSIBLE_BOOT_DEVICE`); do that only on machines you are reprovisioning.

## Container and deployment

- Use `docker compose` (v2). The legacy `docker-compose` v1 can fail to recreate the container after a
  rebuild ("No such image ... has been removed"); `deploy.sh` prefers v2.
- The production compose file has no source mount, so code changes need
  `docker compose up -d --build` (or `./deploy.sh redeploy`); `./deploy.sh restart` alone does not pick
  them up. Use the dev override for hot reload ([README](../README.md#production-vs-development)).
- Data lives in `./data/srv/*` on the host and survives rebuilds.
