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

Seen with Kaspersky Rescue Disk 24 and applies to every Debian **live-boot** system (Debian Live, KRD 24)
that loads its files over the network. On the client screen:

```
Looking for a connected Ethernet interface ... eth0 ? wwan0 ?
Connected wwan0 found
ipconfig: no devices to configure
connect: Network is unreachable
NFS over TCP not available from 192.168.10.170        (repeats, then "Unable to find a live file system")
```

**Cause.** live-boot picks the *first* network interface that reports a link. On a laptop with a cellular
modem (`wwan0`) the modem has "link" immediately, while the wired card gets it a moment later. live-boot
takes the modem, cannot configure it (`no devices to configure`), and never gets an address. The NFS
message is only the last symptom; it does **not** mean the NFS server lacks TCP. Docks, USB adapters and
virtual interfaces can trigger the same thing.

**Fix.** Tell live-boot which card to use, by adding this to the entry's command line:

```
BOOTIF=01-${net0/mac:hexhyp}
```

It is the same parameter pxelinux sets. iPXE replaces `${net0/mac:hexhyp}` with the MAC of the card the
machine booted from, so it is right on every machine. The recipes already add it for KRD 24 and Debian
Live, and **Save Menu warns** about a network live entry that lacks `BOOTIF=`, `ethdevice=` or
`live-netdev=`. Custom entries must include it themselves.

**Confirm from the server** (no need to read the client screen):

- The DHCP log shows a request with vendor class `Linux ipconfig` from the client's MAC after it downloaded
  `vmlinuz` and `initrd` (that is the live system asking for an address).
- `journalctl -u nfs-mountd` shows `authenticated mount request from <client>`.

If neither appears, the live system still has no network: check the machine's NIC id in its `Client info`
line against the live kernel's drivers (an old kernel is possible but has to be checked, not assumed), try
a USB Ethernet adapter, boot a rescue system with a newer kernel (SystemRescue) on the same machine, and
consider `ethdevice-timeout=60` if the link is slow to come up. `rpcinfo -p SERVER` should list NFS v3 over
TCP (modern servers list only TCP, which is normal).

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
