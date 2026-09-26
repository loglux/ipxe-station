"""Boot reports from live systems: the script, reading what comes back, storing it, the API."""

import subprocess
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

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "wget").write_text(
        '#!/bin/sh\nfor a in "$@"; do echo "$a" >> "$SENT/args"; '
        'case $a in --post-file=*) cat "${a#--post-file=}" > "$SENT/body";; esac; done\n'
    )
    (fakebin / "wget").chmod(0o755)
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
    assert names == ["debian_live_1", "debian_live_2"]  # not Kaspersky (own script), not casper


def test_the_chosen_entries_get_the_argument_and_the_rest_do_not(api, menu):
    model, saved = menu
    got = client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_1"]}).json()[
        "entries"
    ]
    assert [e["enabled"] for e in got] == [True, False]
    assert (
        "live-config.hooks=http://${server_ip}:${port}/ipxe/live-report.sh"
        in model.entries[0].cmdline
    )
    assert "live-config.hooks" not in model.entries[1].cmdline
    assert "live-config" not in model.entries[2].cmdline and len(saved) == 1
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
        client.post("/api/boot-reports/entries", json={"enabled": ["ubuntu_live_1"]}).status_code
        == 422
    )
    monkeypatch.setattr(ipxe_routes, "saved_menu", lambda: None)
    assert client.post("/api/boot-reports/entries", json={"enabled": []}).status_code == 404


def test_a_menu_that_does_not_validate_is_not_reported_as_saved(api, menu, monkeypatch):
    monkeypatch.setattr(ipxe_routes, "save_menu", lambda m: {"valid": False, "message": "bad"})
    resp = client.post("/api/boot-reports/entries", json={"enabled": ["debian_live_1"]})
    assert resp.status_code == 422 and "bad" in resp.json()["detail"]
