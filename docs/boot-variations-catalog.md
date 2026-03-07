# Boot Variations Catalog (from `archive`, not legacy migration)

## Purpose

This catalog captures real-world boot variation patterns seen in `archive/TFTP`,
so the current backend/UI can support them as abstractions.

Non-goal: copying old PXELINUX menu structure, old hardcoded paths, or old naming.

## Source Snapshot

Observed in legacy configs under:

- `archive/TFTP/pxelinux.cfg/default`, `linux`, `ubuntu`, `debian`, `windows`, `rescue`, `av`, `dos`, `livecds`

Observed scale in configs:

- many menu entries and repeated variants for the same product (language, mode, transport)
- mixed transport and boot chains in one tree (HTTP, NFS, memdisk, wimboot, localboot)

## Variation Families (what matters to new architecture)

1. Linux kernel+initrd over HTTP
- Typical: distro installer/live boot with `KERNEL http://...` and `initrd=...`
- Parameters vary by distro (`boot=casper`, Debian installer mirror params, etc.)

2. Linux live over NFS
- Typical: `netboot=nfs` + `nfsroot=SERVER:/path`
- Variants include distro-specific flags and optional language/UI flags

3. Linux/utility ISO via memdisk
- Typical: `KERNEL memdisk` + `APPEND iso ... initrd=<iso>`
- Used heavily for rescue/tools/dos utilities

4. Windows PE via wimboot
- Typical: `wimboot` chain with `bootmgr, BCD, boot.sdi, boot.wim`
- Multiple products use the same artifact model with different paths

5. Tool-specific boot styles
- Examples: SystemRescue HTTP/NFS variants, antivirus language variants, vendor rescue media
- Same base product often appears as several boot profiles

6. Navigation/utility entries
- local boot, reboot, poweroff, chain entries
- important as helper actions, not distro resources

## Normalized `boot_method` Set (initial)

1. `linux_http_kernel_initrd`
2. `linux_nfs_live`
3. `linux_http_iso_ram`
4. `memdisk_iso_or_img`
5. `winpe_wimboot`
6. `utility_action` (localboot/reboot/poweroff/chain)

Notes:

- This is intentionally compact; methods are generic and parameterized.
- New distro support should be presets on top of methods, not new hardcoded methods.

## Minimal Parameter Surface (method-oriented)

1. Common
- `label`, `enabled`, `method`, `notes`, `tags`

2. Linux HTTP kernel/initrd
- `kernel_path_or_url`, `initrd_path_or_url`, `cmdline_tokens[]`

3. Linux NFS live
- `kernel_path_or_url`, `initrd_path_or_url`, `nfsroot`, `cmdline_tokens[]`

4. Linux HTTP ISO RAM
- `kernel_path_or_url`, `initrd_path_or_url`, `iso_url`, `cmdline_tokens[]`

5. memdisk ISO/IMG
- `memdisk_mode` (`iso` or `img`), `image_path_or_url`, `extra_tokens[]`

6. WinPE wimboot
- `bootmgr`, `bcd`, `boot_sdi`, `boot_wim`, `extra_tokens[]`

7. Utility action
- `action` (`localboot`, `reboot`, `poweroff`, `chain`)
- optional `chain_target`

## Variant Model (important)

Many legacy entries are the same resource with different runtime flags.

Examples:

- language variants (`lang=en`, `lang=ru`)
- UI mode variants (GUI/text)
- transport variants (NFS vs HTTP/ISO)

Design requirement:

- represent these as variants/profiles under one logical entry family,
  not as unrelated duplicated entries.

## Explicit Non-Goals

1. Do not import legacy menus 1:1 into runtime config.
2. Do not keep hardcoded IPs/host paths from old configs.
3. Do not encode distro logic in frontend.

## Expected Next Tasks

1. Backend contract phase
- add/align schema for method-oriented entries + variants
- keep deterministic generation and backward compatibility

2. Builder UX phase
- method selector
- dynamic fields by method
- variant/profile editor
- keep manual cmdline mode available

3. Assets linkage phase
- resource picker should provide concrete known paths/URLs
- cmdline helper consumes backend-provided concrete values

4. QA phase
- snapshot tests per `boot_method`
- validation tests for required fields and incompatible combinations
- regression tests for existing Ubuntu/Debian/SystemRescue/Kaspersky flows

