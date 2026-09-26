# Boot reports from live systems

A live system started from this server can tell the server how it went: how much memory it has, which disks and
devices it found and which of them have no driver, the state of the battery, kernel errors and missing firmware,
and services that failed. The reports are kept with the machine on the **Devices** tab, so one place shows how
each laptop behaves in each system. It is meant for the day you boot a batch of machines and want to know which
ones need attention, without opening a terminal on any of them.

Checked so far: the collecting script and the server side, tested and run against this server. **Not yet run on
a real Debian Live boot.** [Kaspersky Rescue Disk](kaspersky.md) has its own, older report (firmware and screen).

## Turning it on

**Devices** → *Boot reports from live systems*. It lists the live Linux entries of the menu (entries that boot
with `boot=live`, such as Debian Live); tick the ones that should ask for a report. Ticking adds one argument to
the entry, `live-config.hooks=http://<server>/ipxe/live-report.sh?...`, and saves the menu. Nothing is written to
the boot image. Boot the machine from the network, choose that entry, and about a minute after the desktop
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

The server turns them into a summary: memory, UEFI or BIOS, **battery health** (percent of the design capacity;
under 60% is flagged), **missing firmware**, **devices without a driver** (only for kinds that need one: network,
video, audio, storage, Bluetooth), failed services, the number of kernel messages, and whether Wi-Fi and
Bluetooth are present.

## Where it is kept, and limits

One report per machine and system; a newer one replaces the older. Stored in `data/srv/ipxe/boot-reports.json`
(at most 200 reports; each is cut to 16 KB per section and 120 KB in all, and cleaned of anything but plain
text). **Delete** on a report removes it. The text comes from the machine and is not authenticated; treat it as
a hint, as with the [client info](how-it-works.md#what-the-server-learns-about-a-client).

The two endpoints the live system uses are **open** like `boot.ipxe` (the booting system cannot present a token):
`GET /ipxe/live-report.sh` and `POST /ipxe/boot-report`; see the [security model](how-it-works.md#security-model).
The list and the details are behind the usual token check.

## How it works

`live-config`, which Debian Live uses to set the system up, runs the script named by `live-config.hooks=` early
in boot, as root. The script (made by the server for that machine) installs a small job and an autostart entry;
the job runs once the desktop is up (after 45 seconds), collects the sections and posts them back with
`wget`. It never fails the boot. The mechanism is the same one Kaspersky Rescue Disk uses.

## API

Under `/api/boot-reports`:

| Call | Purpose |
|------|---------|
| `GET /` (`?mac=`) | Reports as summaries, newest first |
| `GET /{id}`, `DELETE /{id}` | One report with all its sections; delete it |
| `GET/POST /entries` | The live entries that can report, and choosing which ones do |

`GET /api/monitoring/clients` also carries each machine's summaries in `boot_reports`.
