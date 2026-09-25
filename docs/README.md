# iPXE Station documentation

| Document | What it answers |
|----------|-----------------|
| [How it works](how-it-works.md) | What runs where, and what happens between pressing F12 and seeing the menu |
| [Boot methods](boot-methods.md) | BIOS PXE, UEFI PXE, UEFI HTTP Boot, Secure Boot, and the Linux/Windows boot modes: what each needs and what is verified |
| [Typical scenarios](scenarios.md) | Ready-made setups: rescue toolkit, live Linux, unattended Debian, your own WinPE automation |
| [Troubleshooting](troubleshooting.md) | The client does not boot, falls back to another device, or WinPE cannot see the disk |
| [Boot variations catalog](boot-variations-catalog.md) | Research notes: the boot patterns the design has to cover |
| [`examples/winpe-provision`](../examples/winpe-provision/README.md) | Scripts and guide for running your own automation in a network-booted WinPE |

The project [README](../README.md) covers installation and the web UI; [ROADMAP](../ROADMAP.md)
tracks what works, what is unverified, and what is planned.

## What is (and is not) in this repository

Only code, scripts and documentation. Boot images and installers (`boot.wim`, ISOs, kernels) live in
`data/srv/`, which git ignores. Keep passwords and keys out of anything under `data/srv/http/`: it is
served over HTTP without authentication.
