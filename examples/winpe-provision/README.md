# WinPE network provisioning example

A small, generic way to run your own automation inside a WinPE that was booted over the network
with iPXE Station (see *Windows PE (wimboot)* in the main [README](../../README.md)).

> **Status: example, not yet validated end to end on hardware.** The WinPE boot itself works (UEFI
> PXE → iPXE → wimboot → WinPE); these two scripts were written for it and still need a full run on
> a real machine. Record what you find in [ROADMAP.md](../../ROADMAP.md).

## How it works

```
PXE → iPXE menu → wimboot → WinPE boots
        └─ X:\Windows\System32\startnet.cmd   (tiny bootstrap, baked into boot.wim)
             1. wpeinit, wait for an IPv4 address
             2. download  http://SERVER/http/provision/start.ps1
             3. run it
                  └─ start.ps1   (lives on the server, change it any time)
                       1. detect vendor and model (WMI)
                       2. download common.zip and models/<vendor>_<model>.zip (both optional)
                       3. unpack them to X:\provision
                       4. drvload every .inf under X:\provision\drivers, then rescan disks
                       5. run X:\provision\run.cmd if the packages contain one
```

Only `startnet.cmd` is inside the WIM. Everything else is served from the server, so you can change
the logic and the per-model payload without rebuilding the image.

## Files

| File | Where it goes |
|------|---------------|
| `startnet.cmd` | Into `boot.wim` as `\Windows\System32\startnet.cmd` (once) |
| `start.ps1` | On the server: `data/srv/http/provision/start.ps1` |

## Setup

**1. Set the server address** in `startnet.cmd` (`PXE_SERVER=host:port`, the UI/HTTP port). It is
baked into the image, so a change of address means repacking the WIM.

**2. Put `startnet.cmd` into `boot.wim`.** Either way keeps a copy of the original first.

Windows (ADK / DISM):

```bat
dism /Mount-Wim /WimFile:boot.wim /Index:1 /MountDir:C:\mount
copy /Y startnet.cmd C:\mount\Windows\System32\startnet.cmd
dism /Unmount-Wim /MountDir:C:\mount /Commit
```

Linux ([wimlib](https://wimlib.net/), package `wimtools`):

```bash
wimupdate boot.wim 1 --command="add startnet.cmd /Windows/System32/startnet.cmd"
```

Optionally add storage drivers at the same time (see *Disk not visible* below):
`dism /Image:C:\mount /Add-Driver /Driver:C:\drivers /Recurse`.

**3. Copy `start.ps1`** to `data/srv/http/provision/` (create the folder) and make sure it is served:

```bash
curl -I http://SERVER:9021/http/provision/start.ps1     # expect 200
```

**4. Add the payload** (optional, see below), then boot a client into the WinPE entry.

## Payload packages

Both packages are optional; a missing one is skipped with a `No package: ...` message.

```
data/srv/http/provision/
├── start.ps1
├── common.zip                          # unpacked on every machine
└── models/
    └── <vendor>_<model>.zip            # unpacked only on that model
```

Inside a zip, use this layout (paths are relative to `X:\provision`):

```
run.cmd            # entry point; started by start.ps1 after unpacking
drivers\...        # any .inf drivers to load with drvload (optional)
...                # your tools and scripts
```

If both zips contain the same file, the model package wins (it is unpacked last).

### Model name (the `<vendor>_<model>` part)

`start.ps1` builds it from WMI: lower-cased, every run of characters other than letters and digits
replaced by `-`. Vendor comes from `Win32_ComputerSystem.Manufacturer`, the model from
`Win32_ComputerSystem.Model` (for Lenovo, from `Win32_ComputerSystemProduct.Version`, because
`Model` holds a machine-type code). For example a `Dell Inc.` / `Latitude 5440` becomes
`dell-inc_latitude-5440`.

The script prints the result when it starts (`Detected: ... -> models/<slug>`), so the easiest way to
get the exact name is to boot the model once and read it from the console.

## Testing without repacking

You can try the server-side part from a WinPE command prompt without changing the image:

```bat
mkdir X:\provision
powershell -NoProfile -Command "(New-Object Net.WebClient).DownloadFile('http://SERVER:9021/http/provision/start.ps1','X:\provision\start.ps1')"
powershell -NoProfile -ExecutionPolicy Bypass -File X:\provision\start.ps1 -Server SERVER:9021
```

With no packages present it only prints the detected model, `No package: ...` and
`No run.cmd ... staying in WinPE`. It changes nothing on the machine.

## Security

- **Whoever can write to `data/srv/http/provision/` controls every machine that boots into this
  WinPE.** `run.cmd` runs inside WinPE with full rights, and WinPE can reach the local disks.
- The `/http/...` files are served **without authentication** (`SECURITY_MODE=token` only protects
  `/api/*`). Use this on a trusted or isolated network.
- Do not put passwords, keys or licence codes into the WinPE image, the zips, or the scripts:
  anything under `data/srv/http/` can be downloaded by anyone who can reach the server.

## Limitations and troubleshooting

- **Server address is baked in.** `PXE_SERVER` in `startnet.cmd` is read once; a new address needs a
  repacked WIM.
- **`X:` is a RAM disk with limited free space** (see DISM `/Set-ScratchSpace`). Large payloads
  should be run from a network share instead of being unpacked to `X:`.
- **No network address.** `startnet.cmd` waits about two minutes, then leaves you at a prompt. Check
  the cable and, for USB Ethernet adapters, that the WinPE image contains their driver.
- **Disk not visible.** With SATA set to "RAID On" (Intel RST/VMD) the NVMe disk is hidden until
  the storage driver is loaded. Either add it to the WIM (`DISM /Add-Driver`) or ship it in the
  model package under `drivers\`; `start.ps1` loads it with `drvload` and rescans.
- **Secure Boot.** The stock iPXE binaries are not signed; see [ROADMAP.md](../../ROADMAP.md) §8.
- **Nothing here is idempotent.** `run.cmd` runs on every boot into this entry; if it changes the
  machine, make it check the state first (or switch the entry off in the Builder when done).
