"""Boot Recipe Engine — auto-generate correct cmdline from detected assets.

Pure functions only; no I/O, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BootOption:
    mode: str  # "squashfs" | "iso" | "http" | "netboot" | "basic"
    label: str  # shown in UI dropdown
    kernel: str
    initrd: str
    cmdline: str
    recommended: bool = field(default=False)


def ubuntu_live_recipe(
    entry: dict, server_ip: str, port: int, nfs_root: str = ""
) -> List[BootOption]:
    """Options for ubuntu_live / ubuntu_netboot / ubuntu_preseed scenarios.

    Ubuntu Server ISO uses a *layered* squashfs (4+ files stacked).  With
    ``fetch=``, casper downloads only one layer and then looks for the rest on
    a physical "medium" (CD/USB) — which does not exist during network boot →
    "no medium found".  The only reliable option for Server ISOs is ``url=``
    (full ISO downloaded to RAM; requires ≥ 4 GB RAM).

    Ubuntu Desktop ISO has a single squashfs, so ``fetch=`` works fine there.

    Detection: if the squashfs filename contains "server" → Server ISO.
    """
    kernel = entry.get("kernel") or ""
    initrd = entry.get("initrd") or ""
    squashfs = entry.get("squashfs")
    iso = entry.get("iso")
    opts: List[BootOption] = []

    # Detect Server ISO from squashfs or ISO filename containing "server"
    is_server = (squashfs is not None and "server" in squashfs.lower()) or (
        iso is not None and "server" in iso.lower()
    )

    # NFS option — works for Server ISO without downloading the full ISO to RAM.
    # casper mounts the NFS path as a "medium" and reads all squashfs layers from it.
    # Requires: NAS NFS export of the host path that maps to /srv/http/<version-dir>/.
    if nfs_root and (kernel or initrd):
        # Derive version directory from kernel path: "ubuntu-22.04/casper/vmlinuz" → "ubuntu-22.04"  # noqa: E501
        version_dir = (kernel or initrd).split("/")[0]
        nfs_path = f"{nfs_root.rstrip('/')}/{version_dir}"
        opts.append(
            BootOption(
                mode="nfs",
                label="NFS — no RAM limit, reads on demand ✅ works for Server",
                kernel=kernel,
                initrd=initrd,
                cmdline=f"ip=dhcp boot=casper netboot=nfs nfsroot={server_ip}:{nfs_path}",
                recommended=is_server,
            )
        )

    if iso:
        iso_url = f"http://{server_ip}:{port}/http/{iso}"
        if is_server:
            label = (
                "ISO — full download to RAM (~2 GB, requires ≥ 4 GB RAM)"
                if nfs_root
                else "ISO — full download to RAM (~2 GB, requires ≥ 4 GB RAM) ✅ works for Server"  # noqa: E501
            )
        else:
            label = "ISO — full download (~2 GB, slow)"
        # Recommend ISO for Server only when NFS is not configured (NFS takes priority)
        opts.append(
            BootOption(
                mode="iso",
                label=label,
                kernel=kernel,
                initrd=initrd,
                cmdline=f"ip=dhcp BOOTIF=01-${{net0/mac:hexhyp}} boot=casper url={iso_url}",
                recommended=is_server and not nfs_root,
            )
        )

    if squashfs:
        squashfs_url = f"http://{server_ip}:{port}/http/{squashfs}"
        label = (
            "Squashfs — fast (~150 MB) ⚠️ Desktop only, will fail on Server ISO"
            if is_server
            else "Squashfs — fast (~150 MB download)"
        )
        opts.append(
            BootOption(
                mode="squashfs",
                label=label,
                kernel=kernel,
                initrd=initrd,
                cmdline=f"ip=dhcp BOOTIF=01-${{net0/mac:hexhyp}} boot=casper fetch={squashfs_url}",
                recommended=not is_server,
            )
        )

    return opts


def systemrescue_recipe(
    entry: dict, server_ip: str, port: int, nfs_root: str = ""
) -> List[BootOption]:
    """Options for systemrescue scenario."""
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
    """Options for kaspersky scenario.

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
    """Options for debian_netboot scenario."""
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
    "ubuntu_netboot": ubuntu_live_recipe,
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
