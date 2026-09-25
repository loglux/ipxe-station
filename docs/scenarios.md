# Typical scenarios

Short recipes for the most common setups. Each links to the detail; nothing here needs more than the
web UI, the files under `data/srv/`, and a client on the same network.

## 1. Rescue toolkit on the LAN

1. **DHCP** tab → start **Proxy DHCP** (no router changes).
2. **Assets** → *Tools & Rescue*: download SystemRescue (or add Hiren's PE / another tool).
3. **Builder** → **+ Add Entry** → pick the scenario and downloaded version → **Create** → **Save Menu**.
4. Boot a client by network (BIOS: F12 network boot; UEFI: the IPv4 PXE entry).

Nothing is written to the client's disk unless you run something that does.

## 2. Live Ubuntu for hardware checks

1. **Assets** → *Ubuntu*: download a Server or Desktop ISO (extraction is automatic).
2. NFS mode (no RAM limit): run `sudo bash scripts/setup-nfs.sh` on the host and set
   **Settings → NFS Boot Root**. Otherwise use the HTTP ISO mode and mind the RAM (Server ≥ 4 GB,
   Desktop ≥ 8 GB).
3. **Builder** → *Ubuntu Live* entry → **Save Menu**.

See [Boot methods](boot-methods.md#linux) for the pitfalls.

## 3. Unattended Debian install

1. **Boot Files** → *preseed.cfg*: create or choose a profile (Debian Minimal or Desktop template),
   edit it, and mark it active (★). It is served at `/preseed.cfg`; named profiles at
   `/preseed/<name>.cfg`.
2. **Builder** → *Debian Preseed* entry → **Save Menu**.

The installer **repartitions and wipes the disk** according to the profile. Try it on a virtual
machine or a spare computer first.

## 4. Your own WinPE with automation

For preparing many machines with your own Windows-side tools.

1. Build a WinPE (Windows ADK) and place `boot.wim`, `BCD`, `boot.sdi` in `data/srv/http/winpe/`
   ([README](../README.md#windows-pe-wimboot)).
2. **Builder** → *Windows PE* entry with kernel `wimboot` and initrd
   `winpe/BCD winpe/boot.sdi winpe/boot.wim`.
3. Bake the small bootstrap `startnet.cmd` into the image and serve `start.ps1` from
   `data/srv/http/provision/`; drop per-model zip packages next to it. Full steps, package layout, the
   model naming rule and security notes:
   [`examples/winpe-provision`](../examples/winpe-provision/README.md).
4. Add the storage driver to the image if your machines use "RAID On" mode.

Clients with Secure Boot on need the plan in [ROADMAP](../ROADMAP.md) §8 (or Secure Boot turned off).

## 5. Use your router's DHCP instead of Proxy DHCP

**DHCP** tab → *Router DHCP config* → choose your server type (dnsmasq, ISC DHCP, MikroTik RouterOS,
Windows Server) → copy the generated settings to it. Run **Check Network DHCP** afterwards to see what
your network actually answers.
