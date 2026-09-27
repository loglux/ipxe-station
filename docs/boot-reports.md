# Boot reports from live systems

A live system started from this server can tell the server how it went: how much memory it has, which disks and
devices it found and which of them have no driver, the state of the battery, kernel errors and missing firmware,
and services that failed. The reports are kept with the machine on the **Devices** tab, so one place shows how
each laptop behaves in each system. It is meant for the day you boot a batch of machines and want to know which
ones need attention, without opening a terminal on any of them.

Checked on a Dell Latitude 5530 with Debian 13 Live started over NFS: the report arrives, and it read correctly
(memory, disks, screen, battery, devices and their drivers). Two Debian 13 quirks had to be worked around, below.
[Kaspersky Rescue Disk](kaspersky.md) has its own, older report (firmware and screen).

## Which entries can send a report

`live-config` has two ways to run a script that comes from the server, and which one works depends on how the
system is started:

- **Over NFS** (`netboot=nfs`): the extracted disk on the server is the medium the system runs from, and
  `live-config` can run a local file, so the entry names the script that sits on the disk
  (`live-config.hooks=file:///run/live/medium/live/config-hooks/ipxe-station-report.sh`, and the same under
  `/lib/live/mount/medium/` for older images). Nothing is downloaded and the image needs nothing. **This is the way
  for Debian Live.** (The obvious `live-config.hooks=medium` does not work on Debian 13: it looks in
  `/lib/live/mount/medium`, and the medium is now at `/run/live/medium`.)
- **Fetching an ISO or squashfs**: the script has to be downloaded by URL, and `live-config` does that with `wget`.
  **Debian 13's live image has curl but no wget, so this fails silently**: the machine boots normally and never asks
  for the script. Images that do have wget (Kaspersky Rescue Disk) work.

The **Devices** page shows this for every live entry: an entry that cannot report is greyed out with the reason.
For Debian Live, add an NFS entry (**Builder** → **+ Add Entry** → *Debian Live* offers an NFS mode once **Settings →
NFS Boot Root** is set).

## Turning it on

**Devices** → *Boot reports from live systems*. It lists the live Linux entries of the menu (entries that boot
with `boot=live`, such as Debian Live); tick the ones that should ask for a report. Ticking adds one argument to
the entry and saves the menu: `live-config.hooks=file://…` for an NFS entry (and the script is put in the disk's
`live/config-hooks/`), or `live-config.hooks=http://<server>/ipxe/live-report.sh?...` where the image has wget.
Unticking removes both. Nothing is written to the boot image itself. Boot the machine from the network, choose that entry, and about a minute after the desktop
starts the report arrives; the machine shows **📋 1 boot report** and, when you open it, the report with facts
and problems as chips. **Show details** loads the full text of every section.

Systems that are not `live-config` based (Ubuntu's `casper`, for one) cannot take part yet; they need a different
way to run a script at start.

## What is collected

Sent once, as plain text, to the server that started the system:

| Section | Content |
|---------|---------|
| System | OS name, kernel, architecture, UEFI or BIOS, uptime |
| Memory, processor | Installed memory and swap, processor model and threads |
| Hardware | Vendor, model, BIOS version and date (**no serial number or UUID**) |
| Disks | Name, size, type, bus and model (no serials) |
| PCI, USB | `lspci -nnk` (with the driver in use) and `lsusb` |
| Network | Interfaces with their MAC addresses, and radio switches (`rfkill`) |
| Screen | Connected outputs and their modes |
| Power | Battery status, charge, cycle count, and capacity against its design capacity |
| Kernel messages | Lines with errors, failures, timeouts, call traces, missing firmware (at most 300) |
| Failed services, journal | `systemctl --failed` and the recent error lines of the journal |

The server turns them into a summary (redone from the stored text whenever the summary learns something new): memory, UEFI or BIOS, **battery health** (percent of the design capacity;
under 60% is flagged), **memory errors** (ECC / machine-check lines, such as `HANDLING IBECC MEMORY ERROR`),
**disk errors** (I/O errors, NVMe resets), **missing firmware** (not counting the Wi-Fi driver's harmless debug
files), **devices without a driver** (only for kinds that need one: network, video, audio, storage, Bluetooth), failed services, the number of kernel messages, and whether Wi-Fi and
Bluetooth are present.

## When a report does not arrive

On the machine, in a terminal, run `curl -s <server>:9021/d | sh`. The script looks at what should have happened
(the kernel command line, what is on the medium, what the hook installed, the `live-config` log, the tools present,
whether the server can be reached), runs the report job once with tracing, prints all of it and sends it to the
server: `GET /api/boot-reports/debug` returns what came back (the last 10). It changes nothing else. This is how
the two Debian 13 problems above were found.

## Where it is kept, and limits

One report per machine and system; a newer one replaces the older. Stored in `data/srv/ipxe/boot-reports.json`
(at most 200 reports; each is cut to 16 KB per section and 120 KB in all, and cleaned of anything but plain
text). **Delete** on a report removes it. The text comes from the machine and is not authenticated; treat it as
a hint, as with the [client info](how-it-works.md#what-the-server-learns-about-a-client).

The two endpoints the live system uses are **open** like `boot.ipxe` (the booting system cannot present a token):
`GET /ipxe/live-report.sh` and `POST /ipxe/boot-report`; see the [security model](how-it-works.md#security-model).
The list and the details are behind the usual token check.

## How it works

`live-config`, which Debian Live uses to set the system up, runs the hooks named by `live-config.hooks=` early in
boot, as root: local files (`file://`) or scripts fetched by URL. The script installs a small job and an
autostart entry; the job runs once the desktop is up (after 45 seconds), collects the sections and sends them
with `curl` (or `wget` where there is no curl). A script that came from the medium does not know the machine, so
the job names it itself: the MAC of the card it network-booted from (`BOOTIF` on the kernel command line, which
the entries carry) and its model from DMI. It never fails the boot. The URL mechanism is the one Kaspersky Rescue
Disk uses.

## API

Under `/api/boot-reports`:

| Call | Purpose |
|------|---------|
| `GET /` (`?mac=`) | Reports as summaries, newest first |
| `GET /{id}`, `DELETE /{id}` | One report with all its sections; delete it |
| `GET/POST /entries` | The live entries that can report, and choosing which ones do |

`GET /api/monitoring/clients` also carries each machine's summaries in `boot_reports`.
