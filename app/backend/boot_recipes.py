"""Boot Recipe Engine — auto-generate correct cmdline from detected assets.

Pure functions only; no I/O, no side effects.

Ubuntu boot method reference (casper docs + community testing):
───────────────────────────────────────────────────────────────
NFS (netboot=nfs):
  - Works for both Server and Desktop ISOs.
  - casper mounts the NFS path as "medium" and reads squashfs layers from it.
  - Requires ``ignore_uuid`` since Ubuntu 20.04+ (UUID in initrd != NFS medium).
  - No large RAM requirement — files read on demand over the network.
  - ``cloud-config-url=/dev/null`` prevents cloud-init double-download on Server.

HTTP ISO (url=):
  - Downloads the full ISO to a RAM disk, then loop-mounts it.
  - ``url=`` must use an IP address — casper initramfs has no DNS resolver.
  - Server ISO (~1.6 GB for 22.04, ~2.1 GB for 24.04): needs ≥ 4 GB RAM.
    Requires ``root=/dev/ram0 ramdisk_size=<KB>`` to allocate sufficient RAM disk.
    ramdisk_size 22.04 → 1 500 000 KB (~1.43 GB); 24.04 → 2 500 000 KB (~2.38 GB).
    Also needs ``cloud-config-url=/dev/null`` to prevent cloud-init re-downloading ISO.
  - Desktop ISO (~5.5 GB): needs ≥ 8 GB RAM.  ``boot=casper`` required (not baked in).

HTTP squashfs (fetch=) — DO NOT USE on Ubuntu 22.04+:
  - Causes black screen or "no medium found" via iPXE.
  - Server ISO uses 4 layered squashfs files; fetch= downloads only one layer and
    casper looks for the remaining layers on a physical "medium" → "no medium found".
  - Desktop ISO has a single squashfs but fetch= is still unreliable on 22.04+ kernels.
  - Confirmed broken: netboot.xyz#1513, ipxe/ipxe discussion #1041.
  - Use NFS instead for squashfs-level efficiency without RAM limits.

24.04 (Noble) additions:
  - ``cloud-init=disabled`` on Desktop prevents cloud-init delays/conflicts.
  - Server ``url=`` same as 22.04 but ISO is larger → bigger ramdisk_size.
  - ``iso-url=`` is the Noble canonical name; ``url=`` is an alias — use ``url=`` for
    compatibility with both 22.04 and 24.04.

BOOTIF:
  - ``BOOTIF=01-${net0/mac:hexhyp}`` tells the installer which interface was used for
    PXE boot.  Useful on multi-NIC machines.  Not consumed by casper — read by
    cloud-init / NetworkManager.  Not included by default; add manually if needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BootOption:
    mode: str  # "nfs" | "iso" | "http" | "netboot"
    label: str  # shown in UI dropdown
    kernel: str
    initrd: str
    cmdline: str
    recommended: bool = field(default=False)


def ubuntu_live_recipe(
    entry: dict, server_ip: str, port: int, nfs_root: str = ""
) -> List[BootOption]:
    """Boot options for Ubuntu Live ISO scenarios (Desktop and Server, 22.04 / 24.04).

    Offered modes:
      nfs    — NFS mount of the extracted ISO directory.  Recommended for Server.
               Requires ``nfs_root`` to be set (Settings → NFS Boot).
      iso    — Full ISO downloaded to RAM via ``url=``.  Fallback when NFS unavailable.

    NOT offered:
      squashfs via fetch= — broken on Ubuntu 22.04+ via iPXE (see module docstring).
    """
    kernel = entry.get("kernel") or ""
    initrd = entry.get("initrd") or ""
    squashfs = entry.get("squashfs")
    iso = entry.get("iso")
    opts: List[BootOption] = []

    # Parse major version for version-specific parameters (22, 24, …)
    ver_str = entry.get("version", "")
    try:
        major_ver = int(ver_str.split(".")[0])
    except (ValueError, IndexError):
        major_ver = 24

    # Server ISO: squashfs filename contains "server", or ISO filename contains "server"
    is_server = (squashfs is not None and "server" in squashfs.lower()) or (
        iso is not None and "server" in iso.lower()
    )

    # Ubuntu 24.04+ Desktop: disable cloud-init in live session to prevent
    # delays / unexpected network reconfiguration during live boot.
    cloud_init_flag = "cloud-init=disabled " if (not is_server and major_ver >= 24) else ""

    # ── NFS option ────────────────────────────────────────────────────────────
    # casper mounts nfsroot as the "medium" and reads all squashfs layers from it.
    # ``ignore_uuid`` is required since 20.04: initrd UUID != NFS medium UUID.
    # ``cloud-config-url=/dev/null`` stops cloud-init from re-downloading the ISO.
    if nfs_root and (kernel or initrd):
        version_dir = (kernel or initrd).split("/")[0]
        nfs_path = f"{nfs_root.rstrip('/')}/{version_dir}"

        if is_server:
            nfs_cmdline = (
                f"ip=dhcp boot=casper netboot=nfs nfsroot={server_ip}:{nfs_path} "
                f"ignore_uuid cloud-config-url=/dev/null"
            )
        else:
            nfs_cmdline = (
                f"ip=dhcp boot=casper netboot=nfs nfsroot={server_ip}:{nfs_path} "
                f"ignore_uuid fsck.mode=skip {cloud_init_flag}quiet splash"
            )

        opts.append(
            BootOption(
                mode="nfs",
                label="NFS — reads on demand, no RAM limit ✅ Server & Desktop",
                kernel=kernel,
                initrd=initrd,
                cmdline=nfs_cmdline.strip(),
                recommended=True,
            )
        )

    # ── HTTP ISO option (url=) ────────────────────────────────────────────────
    # Downloads full ISO to RAM disk, then loop-mounts it.
    # url= must use an IP address — casper initramfs has no DNS resolver.
    if iso:
        iso_url = f"http://{server_ip}:{port}/http/{iso}"

        if is_server:
            # ramdisk_size is in KB.  Ubuntu Server ISO sizes:
            #   22.04 ≈ 1.6 GB → 1 500 000 KB  (tight but documented minimum)
            #   24.04 ≈ 2.1 GB → 2 500 000 KB
            ramdisk_size = 1_500_000 if major_ver < 24 else 2_500_000
            iso_label = (
                f"ISO — to RAM (~{2 if major_ver >= 24 else 1.6:.0f} GB, "
                f"requires ≥ {4 if major_ver >= 24 else 4} GB RAM)"
                + ("" if nfs_root else " ✅ Server")
            )
            iso_cmdline = (
                f"root=/dev/ram0 ramdisk_size={ramdisk_size} ip=dhcp "
                f"cloud-config-url=/dev/null url={iso_url}"
            )
        else:
            iso_label = "ISO — to RAM (~5.5 GB Desktop, requires ≥ 8 GB RAM)"
            iso_cmdline = (
                f"boot=casper ip=dhcp cloud-config-url=/dev/null "
                f"{cloud_init_flag}url={iso_url} quiet splash"
            )

        opts.append(
            BootOption(
                mode="iso",
                label=iso_label,
                kernel=kernel,
                initrd=initrd,
                cmdline=iso_cmdline.strip(),
                # Recommend ISO for Server only when NFS not available
                recommended=is_server and not nfs_root,
            )
        )

    # NOTE: squashfs via fetch= is intentionally NOT offered here.
    # It is broken on Ubuntu 22.04+ via iPXE — causes black screen or
    # "no medium found".  Use NFS for squashfs-level efficiency without RAM limits.

    return opts


def systemrescue_recipe(
    entry: dict, server_ip: str, port: int, nfs_root: str = ""
) -> List[BootOption]:
    """Boot options for SystemRescue scenario."""
    ver = entry.get("version", "")
    prefix = "rescue"
    base_url = f"http://{server_ip}:{port}/http/{prefix}-{ver}/"
    return [
        BootOption(
            mode="http",
            label="SystemRescue via HTTP",
            kernel=entry.get("kernel") or "",
            initrd=entry.get("initrd") or "",
            cmdline=f"ip=dhcp archisobasedir=sysresccd archiso_http_srv={base_url}",
            recommended=True,
        )
    ]


def kaspersky_recipe(
    entry: dict, server_ip: str, port: int, nfs_root: str = ""
) -> List[BootOption]:
    """Boot options for Kaspersky Rescue Disk.

    Two distinct layouts exist:
    - KRD 18: custom kernel k-x86_64 in krd/boot/grub/, uses ``netboot=<http_root>``
    - KRD 24: Debian Live layout in live/, uses ``boot=live components fetch=<url>``

    The layout is detected from the kernel path.
    """
    ver = entry.get("version", "")
    kernel = entry.get("kernel") or ""
    initrd = entry.get("initrd") or ""
    squashfs = entry.get("squashfs")
    iso = entry.get("iso")

    # KRD 18 layout: kernel at krd/boot/grub/k-x86_64
    if "/krd/" in kernel or kernel.endswith(("k-x86_64", "k-x86")):
        krd_root = kernel.split("/krd/")[0] + "/krd/"
        netboot_url = f"http://{server_ip}:{port}/http/{krd_root}"
        return [
            BootOption(
                mode="netboot",
                label="Kaspersky Rescue Disk 18 — HTTP netboot",
                kernel=kernel,
                initrd=initrd,
                cmdline=f"initrd=initrd.xz netboot={netboot_url} net.ifnames=0 lang=en dostartx",
                recommended=True,
            )
        ]

    # KRD 24 layout: Debian Live in live/
    opts: List[BootOption] = []

    if iso:
        iso_url = f"http://{server_ip}:{port}/http/{iso}"
        opts.append(
            BootOption(
                mode="iso",
                label="Kaspersky Rescue Disk 24 — ISO fetch (official, ~660 MB)",
                kernel=kernel,
                initrd=initrd,
                cmdline=f"boot=live components locales=en_US.UTF-8 fetch={iso_url}",
                recommended=True,
            )
        )

    if squashfs:
        squashfs_url = f"http://{server_ip}:{port}/http/{squashfs}"
        opts.append(
            BootOption(
                mode="squashfs",
                label="Kaspersky Rescue Disk 24 — squashfs fetch (~460 MB)",
                kernel=kernel,
                initrd=initrd,
                cmdline=f"boot=live components locales=en_US.UTF-8 fetch={squashfs_url}",
            )
        )

    # Fallback: no files detected yet (KRD 24 assumed)
    if not opts:
        iso_url = f"http://{server_ip}:{port}/http/kaspersky-{ver}/krd-{ver}.iso"
        opts.append(
            BootOption(
                mode="iso",
                label="Kaspersky Rescue Disk — ISO fetch",
                kernel=kernel,
                initrd=initrd,
                cmdline=f"boot=live components locales=en_US.UTF-8 fetch={iso_url}",
                recommended=True,
            )
        )

    return opts


def debian_recipe(entry: dict, server_ip: str, port: int, nfs_root: str = "") -> List[BootOption]:
    """Boot options for Debian net install scenario."""
    return [
        BootOption(
            mode="netboot",
            label="Debian net install",
            kernel=entry.get("kernel") or "",
            initrd=entry.get("initrd") or "",
            cmdline="ip=dhcp auto=true priority=critical",
            recommended=True,
        )
    ]


RECIPE_MAP = {
    "ubuntu_live": ubuntu_live_recipe,
    "ubuntu_netboot": ubuntu_live_recipe,  # same assets, same recipe logic
    "ubuntu_preseed": ubuntu_live_recipe,
    "systemrescue": systemrescue_recipe,
    "kaspersky": kaspersky_recipe,
    "debian_netboot": debian_recipe,
}


def get_recipe(scenario: str, entry: dict, server_ip: str, port: int, nfs_root: str = "") -> dict:
    """Return boot options for a given scenario + catalog entry.

    Returns ``{"options": [...], "error": None}`` on success,
    or ``{"options": [], "error": "reason"}`` when no recipe or no files found.
    """
    fn = RECIPE_MAP.get(scenario)
    if fn is None:
        return {"options": [], "error": f"No recipe for scenario: {scenario}"}

    opts = fn(entry, server_ip, port, nfs_root)
    if not opts:
        return {"options": [], "error": "No bootable files found in this directory."}

    return {
        "options": [
            {
                "mode": o.mode,
                "label": o.label,
                "kernel": o.kernel,
                "initrd": o.initrd,
                "cmdline": o.cmdline,
                "recommended": o.recommended,
            }
            for o in opts
        ],
        "error": None,
    }
