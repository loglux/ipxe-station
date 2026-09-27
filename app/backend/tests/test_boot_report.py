"""Boot reports from live systems: the script, reading what comes back, storing it, the API."""

import base64
import http.server
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.backend.boot_report as br
from app.main import app
from app.routes import ipxe as ipxe_routes
from app.routes import state

client = TestClient(app)

PCI = """\
00:00.0 Host bridge [0600]: Intel Corporation Device [8086:4650] (rev 05)
00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 [8086:46a6] (rev 0c)
\tSubsystem: Dell Device [1028:0b06]
\tKernel driver in use: i915
\tKernel modules: i915
00:14.3 Network controller [0280]: Intel Corporation Alder Lake-P PCH CNVi WiFi [8086:51f0] (rev 01)
\tKernel driver in use: iwlwifi
\tKernel modules: iwlwifi
00:1f.3 Audio device [0403]: Intel Corporation Alder Lake PCH-P High Definition Audio [8086:51c8] (rev 01)
\tKernel modules: snd_hda_intel, snd_sof_pci_intel_tgl
02:00.0 Ethernet controller [0200]: Realtek Semiconductor RTL8111/8168 [10ec:8168] (rev 15)
"""  # noqa: E501

REPORT = f"""\
##### system
os=Debian GNU/Linux 13 (trixie)
kernel=6.12.63+deb13-amd64
arch=x86_64
boot=uefi
uptime_s=61
##### memory
MemTotal:       16123456 kB
SwapTotal:             0 kB
##### cpu
model name\t: 12th Gen Intel(R) Core(TM) i7-1255U
threads=12
##### dmi
sys_vendor=Dell Inc.
product_name=Latitude 5530
bios_version=1.20.0
##### disks
nvme0n1 476.9G disk nvme SAMSUNG MZVL2512HCJQ
##### pci
{PCI}##### usb
Bus 001 Device 003: ID 8087:0033 Intel Corp. AX211 Bluetooth
##### network
wlp0s20f3 UP aa:bb:cc:00:00:01
##### display
card0-eDP-1 connected 1920x1080
##### power
AC type=Mains
BAT0 type=Battery status=Discharging capacity=87 cycle_count=312 energy_full=38000000 energy_full_design=50000000
##### kernel-messages
[    3.1] iwlwifi 0000:00:14.3: firmware: failed to load iwlwifi-so-a0-gf-a0-72.ucode (-2)
[    3.2] iwlwifi 0000:00:14.3: Direct firmware load for iwlwifi-so-a0-gf-a0-72.ucode failed with error -2
[    5.0] nvme nvme0: I/O error, dev nvme0n1
##### failed-units
bluetooth.service loaded failed failed Bluetooth service
##### journal-errors
Sep 26 23:01:02 host something[1]: bad thing happened
"""  # noqa: E501


# --- reading a report ---------------------------------------------------------------


def test_sections_are_split_and_unknown_ones_ignored():
    sections = br.parse_sections(REPORT + "##### secrets\nhunter2\n")
    assert list(sections) == list(br.SECTIONS)
    assert "hunter2" not in "".join(sections.values())
    assert sections["memory"].startswith("MemTotal:")


def test_control_characters_and_oversized_sections_are_cut():
    body = "##### system\nos=x\x1b[31mred\x00\n##### kernel-messages\n" + "A" * (
        br.SECTION_LIMIT * 3
    )
    sections = br.parse_sections(body)
    assert "\x1b" not in sections["system"] and "\x00" not in sections["system"]
    assert len(sections["kernel-messages"]) == br.SECTION_LIMIT


def test_the_whole_report_is_capped():
    body = "".join(f"##### {name}\n" + "x" * br.SECTION_LIMIT + "\n" for name in br.SECTIONS)
    assert sum(len(t) for t in br.parse_sections(body).values()) <= br.TOTAL_LIMIT


def test_the_summary_tells_what_matters():
    s = br.summarize(br.parse_sections(REPORT))
    assert s["os"] == "Debian GNU/Linux 13 (trixie)" and s["kernel"] == "6.12.63+deb13-amd64"
    assert s["boot"] == "uefi" and s["ram_mb"] == 15745 and s["threads"] == 12
    assert "i7-1255U" in s["cpu"] and s["model"] == "Dell Inc. Latitude 5530"
    assert s["kernel_problem_lines"] == 3
    assert s["failed_units"] == ["bluetooth.service"]
    assert s["missing_firmware"] == ["iwlwifi-so-a0-gf-a0-72.ucode"]
    assert s["has_wifi"] and s["has_bluetooth"] and s["journal_errors"] == 1


def test_devices_without_a_driver_are_found_only_where_a_driver_is_expected():
    found = br.devices_without_driver(PCI)
    assert len(found) == 2
    assert any("Audio device" in f for f in found) and any("RTL8111" in f for f in found)
    assert not any("Host bridge" in f for f in found)  # has no driver, and does not need one
    assert not any("WiFi" in f or "VGA" in f for f in found)


def test_the_last_device_in_the_list_is_checked_too():
    assert br.devices_without_driver(PCI.splitlines()[-1]) != []


def test_battery_health_is_worked_out_from_the_design_capacity():
    line = (
        "BAT0 type=Battery status=Discharging capacity=87 cycle_count=312 "
        "energy_full=38000000 energy_full_design=50000000"
    )
    (bat,) = br.batteries("AC type=Mains\n" + line)
    assert bat == {
        "name": "BAT0",
        "status": "Discharging",
        "cycles": "312",
        "charge_pct": 87,
        "health_pct": 76,
    }
    (amp,) = br.batteries("BAT1 type=Battery charge_full=3000 charge_full_design=6000")
    assert amp["health_pct"] == 50
    (bare,) = br.batteries("BAT0 type=Battery status=Full")
    assert "health_pct" not in bare
    assert br.batteries("AC type=Mains") == []


def test_an_empty_or_odd_body_gives_an_empty_summary_not_an_error():
    s = br.summarize(br.parse_sections("nothing useful here"))
    assert (
        s["os"] == "" and s["ram_mb"] == 0 and s["missing_firmware"] == [] and s["batteries"] == []
    )


# --- keeping reports ---------------------------------------------------------------------


DELL = {"mac": "aa:bb:cc:dd:ee:01", "manufacturer": "Dell Inc.", "product": "Latitude 5530"}


def test_one_report_per_machine_and_system_newest_wins(tmp_path):
    path = tmp_path / "r.json"
    first = br.record(path, "10.0.0.5", DELL, REPORT)
    again = br.record(path, "10.0.0.5", DELL, REPORT.replace("uptime_s=61", "uptime_s=99"))
    assert first["id"] == again["id"] and len(br.summaries(path)) == 1
    assert br.summaries(path)[0]["summary"]["uptime_s"] == 99
    ubuntu = br.record(
        path, "10.0.0.5", DELL, REPORT.replace("Debian GNU/Linux 13 (trixie)", "Ubuntu 24.04")
    )
    assert ubuntu["id"] != first["id"] and len(br.summaries(path)) == 2
    br.record(path, "10.0.0.6", {"mac": "aa:bb:cc:dd:ee:02"}, REPORT)
    assert len(br.summaries(path)) == 3


def test_summaries_leave_out_the_text_and_can_be_filtered_by_machine(tmp_path):
    path = tmp_path / "r.json"
    br.record(path, "10.0.0.5", DELL, REPORT)
    br.record(path, "10.0.0.6", {"mac": "aa:bb:cc:dd:ee:02"}, REPORT)
    assert all("sections" not in r for r in br.summaries(path))
    assert [r["mac"] for r in br.summaries(path, DELL["mac"])] == [DELL["mac"]]
    full = br.get(path, br.summaries(path, DELL["mac"])[0]["id"])
    assert "pci" in full["sections"]


def test_delete_and_missing(tmp_path):
    path = tmp_path / "r.json"
    entry = br.record(path, "10.0.0.5", DELL, REPORT)
    assert br.delete(path, entry["id"]) is True and br.delete(path, entry["id"]) is False
    assert br.get(path, entry["id"]) is None


def test_the_store_is_pruned(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "MAX_REPORTS", 3)
    path = tmp_path / "r.json"
    for n in range(5):
        br.record(path, f"10.0.0.{n}", {"mac": f"aa:bb:cc:dd:ee:0{n}"}, REPORT)
    assert len(br.summaries(path)) == 3


def test_a_broken_store_reads_as_empty(tmp_path):
    (tmp_path / "r.json").write_text("{not json")
    assert br.summaries(tmp_path / "r.json") == []


# --- the script ------------------------------------------------------------------------------


def test_report_url_names_the_machine():
    url = br.report_url_for("192.168.10.170:9021", DELL)
    assert url.startswith("http://192.168.10.170:9021/ipxe/boot-report?mac=aa%3Abb")
    assert "product=Latitude+5530" in url and "serial" not in url


def test_only_a_plain_http_address_and_a_sane_delay_reach_the_script():
    url = br.report_url_for("192.168.10.170:9021", DELL)
    assert f'REPORT_URL="{url}"' in br.render_hook(url, 45)
    for hostile in ("http://x/y?a='; rm -rf /; '", "ftp://x/y?a=1", "http://a b/y?c=1"):
        assert hostile not in br.render_hook(hostile)
    assert 'DELAY="600"' in br.render_hook(url, 99999) and 'DELAY="0"' in br.render_hook(url, -5)


def test_the_kernel_argument_uses_the_menus_variables():
    arg = br.hook_argument()
    assert arg.startswith(
        "live-config.hooks=http://${server_ip}:${port}/ipxe/live-report.sh?mac=${net0/mac}"
    )
    assert br.is_hook_token(arg) and not br.is_hook_token("live-config.hooks=http://x/other.sh")


def make_sender(tmp_path):
    """A fake curl and wget that keep what they are asked to send (never post for real)."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir(exist_ok=True)
    (fakebin / "curl").write_text(
        '#!/bin/sh\nfor a in "$@"; do echo "$a" >> "$SENT/args"; '
        'case $a in @*) cat "${a#@}" > "$SENT/body";; esac; done\n'
    )
    (fakebin / "wget").write_text(
        '#!/bin/sh\nfor a in "$@"; do echo "$a" >> "$SENT/args"; '
        'case $a in --post-file=*) cat "${a#--post-file=}" > "$SENT/body";; esac; done\n'
    )
    for name in ("curl", "wget"):
        (fakebin / name).chmod(0o755)
    return fakebin


def run_collector(root, tmp_path, proc=None):
    """Run the installed collector with fake senders; returns (sent dir)."""
    sent = tmp_path / "sent"
    sent.mkdir(exist_ok=True)
    env = {
        "PATH": f"{make_sender(tmp_path)}:/usr/bin:/bin:/usr/sbin:/sbin",
        "IPXE_STATION_CONF": str(root / "etc/ipxe-station-report.conf"),
        "IPXE_STATION_REPORT_DELAY": "0",
        "SENT": str(sent),
    }
    if proc is not None:
        env["IPXE_STATION_PROC"] = str(proc)
    subprocess.run([str(root / "usr/local/bin/ipxe-station-boot-report")], env=env, check=True)
    return sent


def test_the_installed_job_sends_the_sections_and_no_serial_numbers(tmp_path):
    url = br.report_url_for("192.168.10.170:9021", DELL)
    root = tmp_path / "machine"
    script = tmp_path / "hook.sh"
    script.write_text(br.render_hook(url, 0))
    env = {"PATH": "/usr/bin:/bin", "IPXE_STATION_ROOT": str(root)}
    subprocess.run(["sh", str(script)], env=env, check=True)

    assert (root / "etc/xdg/autostart/ipxe-station-boot-report.desktop").read_text().count(
        "Exec="
    ) == 1
    conf = (root / "etc/ipxe-station-report.conf").read_text()
    assert f"REPORT_URL='{url}'" in conf

    fakebin = make_sender(tmp_path)
    sent = tmp_path / "sent"
    sent.mkdir()
    run_env = {
        "PATH": f"{fakebin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "IPXE_STATION_CONF": str(root / "etc/ipxe-station-report.conf"),
        "IPXE_STATION_REPORT_DELAY": "0",
        "SENT": str(sent),
    }
    subprocess.run([str(root / "usr/local/bin/ipxe-station-boot-report")], env=run_env, check=True)

    body = (sent / "body").read_text()
    for name in ("system", "memory", "cpu", "dmi", "kernel-messages"):
        assert f"##### {name}\n" in body
    assert "os=" in body and "MemTotal:" in body
    assert "product_serial" not in body and "product_uuid" not in body
    assert url in (sent / "args").read_text()
    # what the script sends is what the server can read
    sections = br.parse_sections(body)
    assert br.summarize(sections)["ram_mb"] > 0


# --- API -------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    monkeypatch.setattr(state, "INVENTORY_FILE", tmp_path / "clients.json")
    monkeypatch.setattr(state, "_inventory_loaded", False)
    return tmp_path


def post_report(body=REPORT, **params):
    return client.post(
        "/ipxe/boot-report",
        params=params or {"mac": DELL["mac"], "product": "Latitude 5530"},
        content=body.encode(),
    )


def test_the_script_endpoint_serves_a_script_that_reports_back_to_this_server(api):
    got = client.get(
        "/ipxe/live-report.sh",
        params={"mac": DELL["mac"], "product": "Latitude 5530"},
        headers={"host": "192.168.10.170:9021"},
    )
    assert got.status_code == 200 and got.headers["cache-control"] == "no-cache"
    assert "http://192.168.10.170:9021/ipxe/boot-report?mac=aa%3Abb%3Acc%3Add%3Aee%3A01" in got.text


def test_the_cloudinit_endpoints_serve_what_a_machine_needs(api):
    meta = client.get("/ipxe/cloud-init/meta-data")
    assert meta.status_code == 200 and meta.headers["cache-control"] == "no-cache"
    assert "instance-id" in meta.text
    user = client.get("/ipxe/cloud-init/user-data")
    assert user.status_code == 200 and user.text.startswith("#cloud-config\n")
    assert "ipxe-station-boot-report" in user.text
    # cloud-init has been seen retrying a 404 here every second; a clean 200 avoids that
    vendor = client.get("/ipxe/cloud-init/vendor-data")
    assert vendor.status_code == 200 and vendor.text.startswith("#cloud-config\n")


def test_a_posted_report_is_stored_and_listed(api):
    assert post_report().status_code == 204
    reports = client.get("/api/boot-reports").json()["reports"]
    assert len(reports) == 1 and reports[0]["summary"]["os"].startswith("Debian")
    assert "sections" not in reports[0]
    full = client.get(f"/api/boot-reports/{reports[0]['id']}").json()
    assert "pci" in full["sections"]


def test_reports_can_be_filtered_and_deleted(api):
    post_report()
    post_report(mac="aa:bb:cc:dd:ee:02")
    assert len(client.get("/api/boot-reports", params={"mac": DELL["mac"]}).json()["reports"]) == 1
    rid = client.get("/api/boot-reports", params={"mac": DELL["mac"]}).json()["reports"][0]["id"]
    assert client.delete(f"/api/boot-reports/{rid}").json() == {"deleted": True}
    assert client.get(f"/api/boot-reports/{rid}").status_code == 404
    assert client.delete(f"/api/boot-reports/{rid}").status_code == 404


def test_an_oversized_report_is_refused(api):
    big = post_report("x" * (br.MAX_BODY_BYTES + 1))
    assert big.status_code == 413 and client.get("/api/boot-reports").json()["reports"] == []


def test_a_report_shows_up_with_its_machine_in_the_device_list(api):
    state.record_client_inventory(
        "10.0.0.5", {"mac": DELL["mac"], "manufacturer": "Dell Inc.", "product": "Latitude 5530"}
    )
    post_report()
    devices = client.get("/api/monitoring/clients").json()["clients"]
    assert [r["summary"]["os"] for r in devices[0]["boot_reports"]][0].startswith("Debian")
    assert "sections" not in devices[0]["boot_reports"][0]


# --- choosing the menu entries -------------------------------------------------------------


def entry(name, kernel, cmdline):
    return SimpleNamespace(name=name, title=name.title(), kernel=kernel, cmdline=cmdline)


@pytest.fixture
def menu(monkeypatch):
    model = SimpleNamespace(
        entries=[
            entry(
                "debian_live_1",
                "debian-13.3-live-xfce/live/vmlinuz",
                "boot=live components fetch=http://x/y.iso ip=dhcp",
            ),
            entry(
                "debian_live_2",
                "debian-13.3-live-xfce/live/vmlinuz",
                "boot=live components ip=dhcp",
            ),
            entry("kaspersky_1", "kaspersky-24/live/vmlinuz", "boot=live components nomodeset"),
            entry("ubuntu_live_1", "ubuntu-24.04/casper/vmlinuz", "boot=casper netboot=nfs"),
        ]
    )
    saved = []
    monkeypatch.setattr(ipxe_routes, "saved_menu", lambda: model)
    monkeypatch.setattr(
        ipxe_routes, "save_menu", lambda m: saved.append(1) or {"valid": True, "warnings": []}
    )
    return model, saved


def test_only_live_config_systems_can_send_reports(api, menu):
    names = [e["name"] for e in client.get("/api/boot-reports/entries").json()["entries"]]
    # Debian Live and Ubuntu, but not Kaspersky (it has its own script)
    assert names == ["debian_live_1", "debian_live_2", "ubuntu_live_1"]


def test_the_chosen_entries_get_the_argument_and_the_rest_do_not(api, menu):
    model, saved = menu
    got = client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_1"]}).json()[
        "entries"
    ]
    assert [e["enabled"] for e in got] == [True, False, False]
    assert (
        "live-config.hooks=http://${server_ip}:${port}/ipxe/live-report.sh"
        in model.entries[0].cmdline
    )
    assert "live-config.hooks" not in model.entries[1].cmdline
    assert "live-config" not in model.entries[3].cmdline and len(saved) == 1
    assert model.entries[0].cmdline.startswith("boot=live components fetch=http://x/y.iso ip=dhcp")


def test_choosing_again_replaces_and_choosing_nothing_removes(api, menu):
    model, _ = menu
    client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_1", "debian_live_2"]})
    client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_2"]})
    assert "live-config.hooks" not in model.entries[0].cmdline
    assert model.entries[1].cmdline.count("live-config.hooks=") == 1
    client.post("/api/boot-reports/entries", json={"enabled": []})
    assert all("live-config.hooks" not in e.cmdline for e in model.entries)


def test_other_entries_and_a_missing_menu_are_refused_clearly(api, menu, monkeypatch):
    assert (
        client.post("/api/boot-reports/entries", json={"enabled": ["kaspersky_1"]}).status_code
        == 422
    )
    assert (
        client.post("/api/boot-reports/entries", json={"enabled": ["no_such_entry"]}).status_code
        == 422
    )
    monkeypatch.setattr(ipxe_routes, "saved_menu", lambda: None)
    assert client.post("/api/boot-reports/entries", json={"enabled": []}).status_code == 404


def test_a_menu_that_does_not_validate_is_not_reported_as_saved(api, menu, monkeypatch):
    monkeypatch.setattr(ipxe_routes, "save_menu", lambda m: {"valid": False, "message": "bad"})
    resp = client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_1"]})
    assert resp.status_code == 422 and "bad" in resp.json()["detail"]


# --- Ubuntu (casper): cloud-init instead of a layer ---------------------------------------------


def test_a_casper_entry_reports_through_cloud_init(api, menu):
    model, saved = menu
    got = client.post("/api/boot-reports/entries", json={"enabled": ["ubuntu_live_1"]})
    assert got.status_code == 200 and len(saved) == 1
    ubuntu = model.entries[3]
    for arg in br.cloudinit_arguments():
        assert arg in ubuntu.cmdline
    state_ = next(e for e in got.json()["entries"] if e["name"] == "ubuntu_live_1")
    assert state_["enabled"] is True and state_["mode"] == "cloud-init"
    assert "live-config" not in ubuntu.cmdline  # not the Debian way


def test_turning_cloud_init_off_removes_all_three_arguments(api, menu):
    model, _ = menu
    client.post("/api/boot-reports/entries", json={"enabled": ["ubuntu_live_1"]})
    client.post("/api/boot-reports/entries", json={"enabled": []})
    ubuntu = model.entries[3]
    assert "ipxe.report" not in ubuntu.cmdline
    assert "ipxe.mac" not in ubuntu.cmdline
    assert "ds=nocloud-net" not in ubuntu.cmdline
    assert ubuntu.cmdline == "boot=casper netboot=nfs"


def test_a_casper_entry_that_disables_cloud_init_is_refused_with_the_reason(api, menu):
    model, _ = menu
    model.entries.append(
        entry("ubuntu_disabled", "ubuntu-24.04/casper/vmlinuz", "boot=casper cloud-init=disabled")
    )
    resp = client.post("/api/boot-reports/entries", json={"enabled": ["ubuntu_disabled"]})
    assert resp.status_code == 422 and "cloud-init=disabled" in resp.json()["detail"]
    state_ = next(
        e
        for e in client.get("/api/boot-reports/entries").json()["entries"]
        if e["name"] == "ubuntu_disabled"
    )
    assert state_["supported"] is False and "Builder" in state_["reason"]


# --- how the script reaches a machine ------------------------------------------------------------


def test_the_disk_folder_comes_from_the_kernel_path():
    assert br.image_folder("debian-13.3-live-xfce/live/vmlinuz") == "debian-13.3-live-xfce"
    assert br.image_folder("ubuntu-24.04/casper/vmlinuz") == "ubuntu-24.04"
    assert br.image_folder("ubuntu-24.04/boot/vmlinuz") is None
    assert br.image_folder("vmlinuz") is None and br.image_folder("") is None
    assert br.image_folder("../x/live/vmlinuz") is None


def image(tmp_path, packages, name="debian-13.3-live-xfce"):
    live = tmp_path / name / "live"
    live.mkdir(parents=True)
    if packages is not None:
        (live / "filesystem.packages").write_text(packages)
    return name


def test_an_image_without_wget_cannot_take_the_script_by_url(tmp_path):
    name = image(tmp_path, "curl\t8.14\nlive-config\t11.0.5\nwget2\t2.2\n")
    assert br.image_has_wget(tmp_path, name) is False  # wget2 is not wget
    got = br.entry_mode(["boot=live", "fetch=http://x/y.iso"], f"{name}/live/vmlinuz", tmp_path)
    assert got["mode"] == "url" and got["supported"] is False and "no wget" in got["reason"]


def test_an_image_with_wget_or_an_unknown_one_can_take_it_by_url(tmp_path):
    name = image(tmp_path, "wget\t1.21\n", "with-wget")
    assert br.entry_mode(["boot=live"], f"{name}/live/vmlinuz", tmp_path)["supported"] is True
    unknown = br.entry_mode(["boot=live"], "somewhere/live/vmlinuz", tmp_path)
    assert unknown == {"mode": "url", "supported": True, "reason": ""}


def test_an_nfs_entry_reads_the_script_from_the_medium_and_needs_no_wget(tmp_path):
    name = image(tmp_path, "curl\t8.14\n")
    got = br.entry_mode(
        ["boot=live", "netboot=nfs", "nfsroot=x:/y"], f"{name}/live/vmlinuz", tmp_path
    )
    assert got == {"mode": "medium", "supported": True, "reason": ""}
    odd = br.entry_mode(["boot=live", "netboot=nfs"], "vmlinuz", tmp_path)
    assert odd["mode"] == "medium" and odd["supported"] is False


def test_a_casper_entry_reports_through_cloud_init_regardless_of_how_it_boots(tmp_path):
    for tokens in (
        ["boot=casper", "netboot=nfs", "nfsroot=x:/y"],
        ["boot=casper", "url=http://x/y.iso"],
        ["boot=casper"],
    ):
        assert br.entry_mode(tokens, "ubuntu-24.04/casper/vmlinuz", tmp_path) == {
            "mode": "cloud-init",
            "supported": True,
            "reason": "",
        }


@pytest.mark.parametrize("flag", ["cloud-init=disabled", "cloud-init=disable"])
def test_a_casper_entry_that_turns_cloud_init_off_is_refused(tmp_path, flag):
    got = br.entry_mode(["boot=casper", flag], "ubuntu-24.04/casper/vmlinuz", tmp_path)
    assert got["mode"] == "cloud-init" and got["supported"] is False
    assert flag in got["reason"] and "Builder" in got["reason"]


def test_cloudinit_arguments_use_the_menus_variables_and_are_recognised_as_ours():
    args = br.cloudinit_arguments()
    assert args[0] == "ds=nocloud-net;s=http://${server_ip}:${port}/ipxe/cloud-init/"
    assert args[1:] == [
        "ipxe.report=http://${server_ip}:${port}/ipxe/boot-report",
        "ipxe.mac=${net0/mac}",
    ]
    assert all(br.is_hook_token(a) for a in args) and not br.is_hook_token("ds=other;s=1")


def test_cloudinit_meta_data_and_user_data():
    assert "instance-id" in br.cloudinit_meta_data()
    assert br.cloudinit_vendor_data() == "#cloud-config\n{}\n"
    user_data = br.cloudinit_user_data()
    assert user_data.startswith("#cloud-config\n")
    assert "path: /usr/local/bin/ipxe-station-boot-report" in user_data
    assert "permissions: '0755'" in user_data
    assert "ipxe-station-boot-report >/dev/null 2>&1 &" in user_data
    encoded = user_data.split("content: ", 1)[1].splitlines()[0]
    assert base64.b64decode(encoded) == br.COLLECTOR.read_bytes().rstrip(b"\n") + b"\n"


def test_the_medium_hook_is_installed_executable_and_removed_with_its_folder(tmp_path):
    name = image(tmp_path, None)
    path = br.install_medium_hook(tmp_path, name, "http://192.168.10.170:9021/ipxe/boot-report")
    assert path == tmp_path / name / "live/config-hooks/ipxe-station-report.sh"
    assert path.stat().st_mode & 0o111
    assert 'REPORT_URL="http://192.168.10.170:9021/ipxe/boot-report"' in path.read_text()
    assert (
        br.remove_medium_hook(tmp_path, name) is True
        and br.remove_medium_hook(tmp_path, name) is False
    )
    assert not path.parent.exists() and (tmp_path / name / "live").exists()  # only our folder goes


def test_the_medium_hook_refuses_a_folder_that_escapes(tmp_path):
    with pytest.raises(ValueError):
        br.install_medium_hook(tmp_path, "../evil", "http://h:1/ipxe/boot-report")


def test_a_machine_names_itself_when_the_script_came_from_the_medium(tmp_path):
    root = tmp_path / "machine"
    base = "http://192.168.10.170:9021/ipxe/boot-report"
    hook = br.install_medium_hook(tmp_path / "http", "debian", base)
    env = {"PATH": "/usr/bin:/bin", "IPXE_STATION_ROOT": str(root)}
    subprocess.run(["sh", str(hook)], env=env, check=True)
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "cmdline").write_text("boot=live components BOOTIF=01-aa-bb-cc-dd-ee-01 ip=dhcp\n")
    sent = run_collector(root, tmp_path, proc)
    args = (sent / "args").read_text()
    assert f"{base}?mac=aa:bb:cc:dd:ee:01&manufacturer=" in args
    assert "--data-binary" in args  # curl is what Debian's image has
    assert "##### system" in (sent / "body").read_text()


def test_an_address_that_already_names_the_machine_is_used_as_it_is(tmp_path):
    root = tmp_path / "machine"
    url = br.report_url_for("h:1", DELL)
    script = tmp_path / "hook.sh"
    script.write_text(br.render_hook(url, 0))
    subprocess.run(
        ["sh", str(script)],
        env={"PATH": "/usr/bin:/bin", "IPXE_STATION_ROOT": str(root)},
        check=True,
    )
    sent = run_collector(root, tmp_path)
    assert url in (sent / "args").read_text() and "&manufacturer=%" not in (
        sent / "args"
    ).read_text().replace(url, "")


def test_a_plain_report_address_without_a_query_is_accepted_by_the_script_template():
    plain = "http://192.168.10.170:9021/ipxe/boot-report"
    assert f'REPORT_URL="{plain}"' in br.render_hook(plain)
    assert 'REPORT_URL=""' in br.render_hook("http://h/x?y=1&z='$(id)'")


# --- API: modes -------------------------------------------------------------------------------


@pytest.fixture
def disks(tmp_path, monkeypatch):
    """A web root with a Debian image that has curl only, and settings pointing at this server."""
    root = tmp_path / "http"
    image(root, "curl\t8.14\n")
    monkeypatch.setattr(state, "HTTP_ROOT", root)
    monkeypatch.setattr(
        state,
        "load_settings",
        lambda: SimpleNamespace(server_ip="192.168.10.170", http_port=9021),
    )
    return root


NFS_LINE = (
    "boot=live components netboot=nfs "
    "nfsroot=${server_ip}:${nfs_root}/debian-13.3-live-xfce ip=dhcp"
)


def test_entries_say_which_mode_they_can_use_and_why_not(api, menu, disks):
    model, _ = menu
    model.entries.append(entry("debian_live_nfs", "debian-13.3-live-xfce/live/vmlinuz", NFS_LINE))
    got = {e["name"]: e for e in client.get("/api/boot-reports/entries").json()["entries"]}
    assert (
        got["debian_live_1"]["supported"] is False and "no wget" in got["debian_live_1"]["reason"]
    )
    assert (
        got["debian_live_nfs"]["mode"] == "medium" and got["debian_live_nfs"]["supported"] is True
    )


def test_an_entry_that_cannot_run_the_script_is_refused_with_the_reason(api, menu, disks):
    resp = client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_1"]})
    assert resp.status_code == 422 and "no wget" in resp.json()["detail"]


def test_an_nfs_entry_gets_the_medium_argument_and_the_file_on_the_disk(api, menu, disks):
    model, saved = menu
    model.entries.append(entry("debian_live_nfs", "debian-13.3-live-xfce/live/vmlinuz", NFS_LINE))
    got = client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_nfs"]})
    assert got.status_code == 200
    nfs = model.entries[-1]
    assert nfs.cmdline.split()[-1] == br.MEDIUM_HOOK_ARG and len(saved) == 1
    hook = disks / "debian-13.3-live-xfce/live/config-hooks/ipxe-station-report.sh"
    assert 'REPORT_URL="http://192.168.10.170:9021/ipxe/boot-report"' in hook.read_text()
    assert [e["enabled"] for e in got.json()["entries"] if e["name"] == "debian_live_nfs"] == [True]


def test_turning_the_nfs_entry_off_removes_the_argument_and_the_file(api, menu, disks):
    model, _ = menu
    model.entries.append(entry("debian_live_nfs", "debian-13.3-live-xfce/live/vmlinuz", NFS_LINE))
    client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_nfs"]})
    client.post("/api/boot-reports/entries", json={"enabled": []})
    assert "live-config.hooks" not in model.entries[-1].cmdline
    assert not (disks / "debian-13.3-live-xfce/live/config-hooks").exists()


def test_the_file_stays_while_any_nfs_entry_of_the_disk_still_asks(api, menu, disks):
    model, _ = menu
    model.entries.append(entry("nfs_a", "debian-13.3-live-xfce/live/vmlinuz", NFS_LINE))
    model.entries.append(entry("nfs_b", "debian-13.3-live-xfce/live/vmlinuz", NFS_LINE))
    client.post("/api/boot-reports/entries", json={"enabled": ["nfs_a", "nfs_b"]})
    client.post("/api/boot-reports/entries", json={"enabled": ["nfs_b"]})
    assert (disks / "debian-13.3-live-xfce/live/config-hooks/ipxe-station-report.sh").exists()
    assert model.entries[-2].cmdline.count("live-config.hooks") == 0
    assert model.entries[-1].cmdline.count(br.MEDIUM_HOOK_ARG) == 1


# --- finding out why a report did not arrive ------------------------------------------------


def test_the_short_address_serves_the_diagnostic_script_for_this_server(api):
    got = client.get("/d", headers={"host": "192.168.10.170:9021"})
    assert got.status_code == 200 and got.headers["cache-control"] == "no-cache"
    assert 'SERVER_URL="http://192.168.10.170:9021"' in got.text


def test_only_a_plain_host_reaches_the_diagnostic_script():
    assert 'SERVER_URL=""' in br.render_debug_script("x'; rm -rf /; '")
    assert 'SERVER_URL="http://h:1"' in br.render_debug_script("h:1")


def test_a_diagnostic_report_is_kept_and_listed_newest_first(api):
    assert client.post("/ipxe/boot-report-debug", content=b"== first\nhello").status_code == 204
    client.post("/ipxe/boot-report-debug", content=b"== second\x1b[31m")
    got = client.get("/api/boot-reports/debug").json()["reports"]
    assert [r["text"].splitlines()[0] for r in got] == ["== second[31m", "== first"]
    assert "\x1b" not in got[0]["text"]


def test_diagnostic_reports_are_limited_in_size_and_number(api):
    assert (
        client.post("/ipxe/boot-report-debug", content=b"x" * (br.MAX_BODY_BYTES + 1)).status_code
        == 413
    )
    for n in range(br.MAX_DEBUG + 3):
        client.post("/ipxe/boot-report-debug", content=f"run {n}".encode())
    got = client.get("/api/boot-reports/debug").json()["reports"]
    assert len(got) == br.MAX_DEBUG and got[0]["text"] == f"run {br.MAX_DEBUG + 2}"


def test_the_diagnostic_script_looks_around_runs_the_job_and_sends_what_it_finds(tmp_path):
    fakebin = make_sender(tmp_path)
    sent = tmp_path / "sent"
    sent.mkdir()
    script = tmp_path / "debug.sh"
    script.write_text(br.render_debug_script("192.168.10.170:9021"))
    done = subprocess.run(
        ["sh", str(script)],
        env={"PATH": f"{fakebin}:/usr/bin:/bin", "SENT": str(sent)},
        capture_output=True,
        text=True,
    )
    for heading in (
        "kernel command line",
        "hooks on the medium",
        "what the hook installed",
        "tools",
        "running the report job",
    ):
        assert f"== {heading}" in done.stdout
    assert "the job is not installed" in done.stdout  # nothing was installed on this machine
    assert "http://192.168.10.170:9021/ipxe/boot-report-debug" in (sent / "args").read_text()
    assert "== kernel command line" in (sent / "body").read_text()
    assert "--- sent to the server" in done.stdout


def test_the_medium_argument_names_the_file_under_the_path_debian_13_uses():
    arg = br.MEDIUM_HOOK_ARG
    assert arg.startswith(
        "live-config.hooks=file:///run/live/medium/live/config-hooks/ipxe-station-report.sh"
    )
    assert "|file:///lib/live/mount/medium/live/config-hooks/ipxe-station-report.sh" in arg
    assert " " not in arg and br.is_hook_token(arg)


def test_the_older_medium_form_is_recognised_and_replaced(api, menu, disks):
    model, _ = menu
    model.entries.append(
        entry(
            "nfs_old", "debian-13.3-live-xfce/live/vmlinuz", NFS_LINE + " live-config.hooks=medium"
        )
    )
    assert br.is_hook_token("live-config.hooks=medium")
    client.post("/api/boot-reports/entries", json={"enabled": ["nfs_old"]})
    tokens = model.entries[-1].cmdline.split()
    assert "live-config.hooks=medium" not in tokens and tokens.count(br.MEDIUM_HOOK_ARG) == 1


# --- what the summary singles out ----------------------------------------------------------------

# Lines a Dell Latitude 5530 really printed in Debian Live.
LAPTOP_KERNEL = """\
[    1.661342] pci 10000:e0:06.0: bridge window [io  size 0x1000]: failed to assign
[   11.057607] EDAC igen6 MC1: HANDLING IBECC MEMORY ERROR
[   11.057609] EDAC igen6 MC0: HANDLING IBECC MEMORY ERROR
[   11.469701] iwlwifi 0000:00:14.3: firmware: failed to load iwl-debug-yoyo.bin (-2)
[   11.472070] iwlwifi 0000:00:14.3: firmware: failed to load iwl-debug-yoyo.bin (-2)
"""


def summary_of(kernel_lines):
    return br.summarize(br.parse_sections("##### kernel-messages\n" + kernel_lines))


def test_memory_errors_are_counted_on_their_own():
    s = summary_of(LAPTOP_KERNEL)
    assert s["memory_errors"] == 2 and s["disk_errors"] == 0
    assert s["kernel_problem_lines"] == 5  # the plain count still counts everything


@pytest.mark.parametrize(
    "line",
    [
        "[  5.0] nvme nvme0: I/O error, dev nvme0n1",
        "[  5.0] blk_update_request: I/O error, dev sda, sector 123",
        "[  5.0] Buffer I/O error on dev sda1",
        "[  5.0] ata1.00: failed command: READ DMA",
        "[  5.0] nvme nvme0: controller reset",
        "[  5.0] critical medium error, dev sda",
    ],
)
def test_disk_errors_are_recognised(line):
    assert summary_of(line + "\n")["disk_errors"] == 1


@pytest.mark.parametrize(
    "line",
    [
        "[  5.0] EDAC MC0: 1 CE memory read error",
        "[  5.0] mce: [Hardware Error]: Machine check events logged",
        "[  5.0] EDAC igen6 MC0: HANDLING IBECC MEMORY ERROR",
        "[  5.0] Uncorrected memory error",
    ],
)
def test_memory_errors_are_recognised(line):
    assert summary_of(line + "\n")["memory_errors"] == 1


def test_ordinary_failures_are_neither_memory_nor_disk_errors():
    s = summary_of("[  1.6] pci 10000:e0:06.0: bridge window [io  size 0x1000]: failed to assign\n")
    assert s["memory_errors"] == 0 and s["disk_errors"] == 0 and s["kernel_problem_lines"] == 1


def test_wifi_debug_firmware_is_not_reported_as_missing_but_real_firmware_is():
    real = (
        "[  3.1] iwlwifi 0000:00:14.3: firmware: failed to load iwlwifi-so-a0-gf-a0-72.ucode (-2)\n"
    )
    s = summary_of(LAPTOP_KERNEL + real)
    assert s["missing_firmware"] == ["iwlwifi-so-a0-gf-a0-72.ucode"]
    assert summary_of(LAPTOP_KERNEL)["missing_firmware"] == []


def test_a_report_stored_before_the_summary_learnt_something_is_summarised_again(tmp_path):
    path = tmp_path / "r.json"
    entry = br.record(path, "10.0.0.5", DELL, "##### kernel-messages\n" + LAPTOP_KERNEL)
    stored = br._load(path)
    stored[0]["summary"] = {"os": "old"}
    stored[0]["v"] = 1
    br._save(path, stored)
    fresh = br.summaries(path)[0]
    assert fresh["summary"]["memory_errors"] == 2 and fresh["v"] == br.SUMMARY_VERSION
    assert br.get(path, entry["id"])["summary"]["memory_errors"] == 2
    assert br._load(path)[0]["v"] == br.SUMMARY_VERSION  # and it is kept


# --- the collector reads its address from the kernel command line -------------------------------


def test_a_machine_with_the_layer_takes_its_address_and_mac_from_the_kernel_command_line(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "cmdline").write_text(
        "boot=casper netboot=nfs ipxe.report=http://192.168.10.170:9021/ipxe/boot-report "
        "ipxe.mac=aa:bb:cc:dd:ee:07 quiet\n"
    )
    root = tmp_path / "machine"
    collector = root / "usr/local/bin"
    collector.mkdir(parents=True)
    (collector / "ipxe-station-boot-report").write_text(br.COLLECTOR.read_text())
    (collector / "ipxe-station-boot-report").chmod(0o755)
    (root / "etc").mkdir()  # no conf file: nothing but the command line to go on
    sent = run_collector(root, tmp_path, proc)
    args = (sent / "args").read_text()
    assert "http://192.168.10.170:9021/ipxe/boot-report?mac=aa:bb:cc:dd:ee:07&manufacturer=" in args


def test_a_machine_without_the_parameter_or_a_conf_sends_nothing(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "cmdline").write_text("boot=casper quiet\n")
    root = tmp_path / "machine"
    (root / "usr/local/bin").mkdir(parents=True)
    (root / "usr/local/bin/ipxe-station-boot-report").write_text(br.COLLECTOR.read_text())
    (root / "usr/local/bin/ipxe-station-boot-report").chmod(0o755)
    (root / "etc").mkdir()
    sent = run_collector(root, tmp_path, proc)
    assert not (sent / "args").exists()


def test_with_neither_curl_nor_wget_the_report_goes_by_python(tmp_path):
    """Ubuntu Desktop's live image has neither; it has python3."""
    received = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            received["path"] = self.path
            received["body"] = self.rfile.read(int(self.headers["Content-Length"])).decode()
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        tools = tmp_path / "tools"
        tools.mkdir()
        for name in (
            "sh",
            "tr",
            "sed",
            "head",
            "tail",
            "cat",
            "cut",
            "grep",
            "mktemp",
            "sleep",
            "uname",
            "rm",
            "python3",
            "basename",
            "id",
        ):
            found = shutil.which(name)
            if found:
                (tools / name).symlink_to(found)
        proc = tmp_path / "proc"
        proc.mkdir()
        (proc / "cmdline").write_text(
            f"ipxe.report=http://127.0.0.1:{server.server_port}/ipxe/boot-report "
            "ipxe.mac=aa:bb:cc:dd:ee:09\n"
        )
        env = {
            "PATH": str(tools),
            "IPXE_STATION_PROC": str(proc),
            "IPXE_STATION_REPORT_DELAY": "0",
            "IPXE_STATION_CONF": "/nonexistent",
        }
        collector = tmp_path / "collector.sh"
        collector.write_text(br.COLLECTOR.read_text())
        subprocess.run([str(tools / "sh"), str(collector)], env=env, check=True)
    finally:
        server.shutdown()
    assert received["path"].startswith("/ipxe/boot-report?mac=aa:bb:cc:dd:ee:09")
    assert "##### system" in received["body"]
