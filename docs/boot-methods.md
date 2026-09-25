# Boot methods

Two separate questions: **how the client gets its first boot file** (firmware level), and **what it
boots afterwards** (Linux, rescue tools, WinPE). "Verified" below means confirmed on real hardware,
as tracked in [ROADMAP](../ROADMAP.md).

## 1. How the client starts

| Method | Client firmware | First file | Status |
|--------|-----------------|------------|--------|
| **BIOS PXE** | Legacy BIOS | `undionly.kpxe` over TFTP | Verified on a BIOS laptop |
| **UEFI PXE** | UEFI (network stack on) | `ipxe.efi` over TFTP | Verified on a Dell laptop, Secure Boot off (2026-09-19) |
| **UEFI HTTP Boot** | UEFI with native HTTP Boot | `ipxe.efi` over HTTP, no TFTP hop | Experimental, **not yet verified** on hardware |
| Router-provided PXE | Any of the above | Depends on your DHCP settings | The DHCP tab generates configs for dnsmasq, ISC DHCP, MikroTik and Windows Server |

Notes:

- On a UEFI machine pick the **IPv4 network** entry in the one-time boot menu. Entries such as
  "UEFI HTTPS Boot" need a boot URL configured in the firmware and an HTTPS server; iPXE Station serves
  plain HTTP, so use the regular IPv4 PXE entry.
- VirtualBox's BIOS PXE does not work with iPXE's UNDI driver (unicast TFTP/HTTP fails). Real hardware
  and other hypervisors are fine.

### Secure Boot

The stock `ipxe.efi` and `snponly.efi` carry **no** Secure Boot signature, so firmware with Secure
Boot on refuses them: turn Secure Boot off for provisioning, or wait for the signing option
([ROADMAP](../ROADMAP.md) §8, own key enrolled in your machines). `wimboot` v2.9.0 is already signed by
Microsoft. HTTP Boot does not avoid the problem, because the firmware still verifies the `.efi` file.
Let's Encrypt is unrelated: it issues TLS certificates, not code-signing trust for firmware.

## 2. What the client boots

### Linux

| Mode | How it works | Needs |
|------|--------------|-------|
| **Live over NFS** (recommended for Ubuntu Server) | Kernel and initrd come over HTTP; the live system then reads its squashfs from an NFS export on demand | An NFS export of `data/srv/http` (`scripts/setup-nfs.sh`, then **Settings → NFS Boot Root**). No RAM limit |
| **Live over HTTP ISO** (`url=`) | The whole ISO is downloaded into RAM | Ubuntu Server ≥ 4 GB RAM, Desktop ≥ 8 GB |
| **Netboot / preseed installer** | Debian installer kernel and initrd; optional unattended install from a preseed profile | Internet or a mirror; a preseed profile for unattended installs |
| **Rescue ISO/netboot** | SystemRescue over HTTP; Kaspersky Rescue Disk (KRD 18 netboot, KRD 24 ISO fetch); GParted; Clonezilla (manual ISO); Memtest86+ | The asset downloaded or added in Assets |

Known pitfalls (from real boots):

- Ubuntu 22.04+ with `fetch=` on the squashfs fails via iPXE ("no medium found"): do not use it.
- `root=/dev/nfs` is for a kernel-NFS root, not for casper live boot: do not add it to casper command
  lines.
- **live-boot** systems (Debian Live, Kaspersky Rescue Disk 24) choose the first network interface with a
  link; on laptops with a cellular modem that is `wwan0`, and the boot dies with "NFS over TCP not
  available". Their command lines must contain `BOOTIF=01-${net0/mac:hexhyp}` (the recipes add it, and
  Save Menu warns when it is missing). Details in [Troubleshooting](troubleshooting.md).
- Debian Live is an **experimental** prototype ([README](../README.md) has its validation checklist).

### Windows PE (wimboot)

[wimboot](https://ipxe.org/wimboot) loads a WinPE image over HTTP with three files (`BCD`,
`boot.sdi`, `boot.wim`), plus `bootmgr` if you supply one. The whole WIM lands in the client's RAM
(allow 2-4 GB). Layout and gotchas are in the [README](../README.md#windows-pe-wimboot); to run your own
automation inside it, see [`examples/winpe-provision`](../examples/winpe-provision/README.md).

Two things bite in practice:

- **Disk not visible:** with SATA set to "RAID On" (Intel RST/VMD) the NVMe disk stays hidden until the
  storage driver is present in WinPE.
- **Secure Boot:** see above.

## Choosing quickly

| I want to... | Use |
|--------------|-----|
| Look at a machine or rescue it | SystemRescue or Hiren's PE entry |
| Test hardware without installing | Ubuntu live over NFS (or HTTP ISO if you have the RAM) |
| Install Debian unattended | Debian Preseed entry with a preseed profile |
| Run my own Windows-side tooling | Your WinPE via wimboot + [`winpe-provision`](../examples/winpe-provision/README.md) |
| Avoid touching my DHCP server | Proxy DHCP (DHCP tab) |
