"""Text size for Kaspersky Rescue Disk: the script the machine runs, and the server's decision."""

import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.backend.krd_display as kd
from app.backend.krd_display import DisplayRule, DisplaySettings
from app.main import app
from app.routes import ipxe as ipxe_routes
from app.routes import state

client = TestClient(app)
SH = shutil.which("dash") or shutil.which("sh")


# --- the script, run for real on a made-up /sys ------------------------------------


def edid(width_mm: int) -> bytes:
    """128 EDID bytes that carry only what the script reads: the image width, twice."""
    data = bytearray(128)
    data[21] = round(width_mm / 10)
    data[66] = width_mm & 0xFF
    data[68] = (width_mm >> 8) << 4
    return bytes(data)


class Machine:
    """A fake root with /sys and the places the script writes to."""

    def __init__(self, root):
        self.root = root
        self.sys = root / "sys"

    def panel(self, mode, width_mm, connector="card0-eDP-1", connected=True):
        d = self.sys / "class" / "drm" / connector
        d.mkdir(parents=True)
        (d / "status").write_text("connected\n" if connected else "disconnected\n")
        (d / "modes").write_text(mode + "\n")
        (d / "edid").write_bytes(edid(width_mm))

    def framebuffer(self, size, chassis="10"):
        (self.sys / "class" / "graphics" / "fb0").mkdir(parents=True)
        (self.sys / "class" / "graphics" / "fb0" / "virtual_size").write_text(size + "\n")
        (self.sys / "class" / "dmi" / "id").mkdir(parents=True)
        (self.sys / "class" / "dmi" / "id" / "chassis_type").write_text(chassis + "\n")

    def run(self, scale, extra_env=None):
        (self.root / "usr/share/glib-2.0/schemas").mkdir(parents=True, exist_ok=True)
        script = self.root / "hook.sh"
        script.write_text(kd.render_hook(scale))
        env = {
            "PATH": "/usr/bin:/bin",
            "IPXE_STATION_SYS": str(self.sys),
            "IPXE_STATION_ROOT": str(self.root),
            **(extra_env or {}),
        }
        done = subprocess.run([SH, str(script)], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return self

    @property
    def factor(self):
        f = self.root / "usr/share/glib-2.0/schemas/99_ipxe-station.gschema.override"
        if not f.exists():
            return None
        return float(f.read_text().split("text-scaling-factor=")[1].split()[0])

    @property
    def xft_dpi(self):
        f = self.root / "etc/X11/Xresources/99-ipxe-station"
        return int(f.read_text().split(":")[1]) if f.exists() else None

    @property
    def log(self):
        f = self.root / "var/log/ipxe-station-display.log"
        return f.read_text() if f.exists() else ""


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


def test_auto_scales_a_full_hd_laptop_panel_from_its_edid(machine):
    machine.panel("1920x1080", 344)  # 15.6 inch
    machine.run("auto")
    assert machine.factor == 1.5
    assert machine.xft_dpi == 144
    assert "from EDID" in machine.log


def test_auto_leaves_a_desktop_monitor_alone(machine):
    machine.panel("1920x1080", 531, connector="card0-HDMI-A-1")  # 24 inch
    machine.run("auto")
    assert machine.factor is None and machine.xft_dpi is None


def test_auto_on_a_4k_panel_only_adds_what_cinnamons_own_doubling_does_not(machine):
    machine.panel("3840x2160", 344)
    machine.run("auto")
    assert machine.factor == 1.5


def test_auto_prefers_the_laptop_panel_over_an_external_monitor(machine):
    machine.panel("1920x1080", 531, connector="card0-HDMI-A-1")
    machine.panel("1920x1080", 344, connector="card0-eDP-1")
    machine.run("auto")
    assert machine.factor == 1.5


def test_auto_ignores_a_disconnected_connector(machine):
    machine.panel("1920x1080", 344, connected=False)
    machine.run("auto")
    assert machine.factor is None


def test_auto_without_a_video_driver_guesses_for_laptops(machine):
    machine.framebuffer("1920,1080", chassis="10")
    machine.run("auto")
    assert machine.factor == 1.5
    assert "assumed" in machine.log


def test_auto_without_a_video_driver_does_not_guess_for_desktops(machine):
    machine.framebuffer("1920,1080", chassis="3")
    machine.run("auto")
    assert machine.factor is None


def test_auto_with_nothing_to_go_on_changes_nothing(machine):
    machine.run("auto")
    assert machine.factor is None
    assert "could not work it out" in machine.log


@pytest.mark.parametrize(
    "scale, factor, dpi",
    [("1.5", 1.5, 144), ("2", 2.0, 192), ("1.25", 1.25, 120), ("2.25", 2.25, 216)],
)
def test_a_fixed_scale_is_applied_as_given(machine, scale, factor, dpi):
    machine.run(scale)
    assert machine.factor == factor
    assert machine.xft_dpi == dpi


def test_off_and_one_hundred_percent_change_nothing(machine):
    machine.run("off")
    assert machine.factor is None
    machine.run("1")
    assert machine.factor is None


def test_the_script_never_fails_the_boot_on_garbage(machine):
    machine.root.joinpath("bad.sh").write_text(
        kd.HOOK_TEMPLATE.read_text().replace("__SCALE__", "banana")
    )
    env = {"PATH": "/usr/bin:/bin", "IPXE_STATION_ROOT": str(machine.root)}
    done = subprocess.run([SH, str(machine.root / "bad.sh")], env=env, capture_output=True)
    assert done.returncode == 0
    assert machine.factor is None


def test_an_unchecked_value_never_reaches_the_script():
    script = kd.render_hook('1"; rm -rf /; "')
    assert 'SCALE="off"' in script and "rm -rf" not in script


# --- the server's decision ---------------------------------------------------------


def test_scale_validation():
    for good in ("off", "auto", "1", "1.5", "2.25", "3"):
        assert kd.valid_scale(good), good
    for bad in ("", "0.5", "3.5", "4", "1.555", "x", "1,5", "-1"):
        assert not kd.valid_scale(bad), bad


def test_first_matching_rule_wins_then_the_default():
    settings = DisplaySettings(
        default="auto",
        rules=[
            DisplayRule(title="5530", match={"product": "Latitude 5530"}, scale="1.5"),
            DisplayRule(match={"manufacturer": "Dell*"}, scale="1.25"),
        ],
    )
    assert kd.resolve_scale(
        settings, {"manufacturer": "Dell Inc.", "product": "Latitude 5530"}
    ) == (
        "1.5",
        "5530",
    )
    assert kd.resolve_scale(settings, {"manufacturer": "Dell Inc.", "product": "XPS"})[0] == "1.25"
    assert kd.resolve_scale(settings, {"manufacturer": "HP"}) == ("auto", "default")


def test_a_rule_needs_something_to_match_and_only_known_fields():
    with pytest.raises(ValueError):
        DisplayRule(match={}, scale="1.5")
    with pytest.raises(ValueError):
        DisplayRule(match={"colour": "red"}, scale="1.5")
    with pytest.raises(ValueError):
        DisplayRule(match={"product": "x"}, scale="huge")


# --- API ---------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    return tmp_path


def test_hook_endpoint_serves_a_script_with_the_servers_decision(api):
    client.put(
        "/api/kaspersky/display",
        json={"default": "auto", "rules": [{"match": {"product": "Latitude*"}, "scale": "1.75"}]},
    )
    hit = client.get(
        "/ipxe/krd-display.sh", params={"manufacturer": "Dell Inc.", "product": "Latitude 5530"}
    )
    assert hit.status_code == 200 and 'SCALE="1.75"' in hit.text
    assert hit.headers["cache-control"] == "no-cache"
    other = client.get("/ipxe/krd-display.sh", params={"product": "ThinkPad"})
    assert 'SCALE="auto"' in other.text


def test_hook_endpoint_without_settings_uses_auto(api):
    assert 'SCALE="auto"' in client.get("/ipxe/krd-display.sh").text


def test_settings_are_validated_and_stored(api):
    assert (
        client.put("/api/kaspersky/display", json={"default": "huge", "rules": []}).status_code
        == 422
    )
    assert (
        client.put("/api/kaspersky/display", json={"default": "1.5", "rules": []}).status_code
        == 200
    )
    assert client.get("/api/kaspersky/display").json()["default"] == "1.5"


def test_preview_says_what_a_machine_would_get(api):
    client.put(
        "/api/kaspersky/display",
        json={
            "default": "off",
            "rules": [{"title": "Dells", "match": {"manufacturer": "Dell*"}, "scale": "2"}],
        },
    )
    got = client.get("/api/kaspersky/display/preview", params={"manufacturer": "Dell Inc."}).json()
    assert got == {"scale": "2", "source": "Dells"}


# --- the menu entries ---------------------------------------------------------------


def krd_entry(cmdline, name="kaspersky_1"):
    return SimpleNamespace(
        name=name, title="Kaspersky", kernel="kaspersky-24/live/vmlinuz", cmdline=cmdline
    )


BASE = (
    "boot=live components netboot=nfs nfsroot=${server_ip}:${nfs_root}/kaspersky-24 "
    "nomodeset BOOTIF=01-x"
)


@pytest.fixture
def menu(monkeypatch):
    model = SimpleNamespace(
        entries=[
            krd_entry(BASE),
            SimpleNamespace(
                name="ubuntu", title="U", kernel="ubuntu/vmlinuz", cmdline="boot=casper nomodeset"
            ),
        ]
    )
    saved = []
    monkeypatch.setattr(ipxe_routes, "saved_menu", lambda: model)
    monkeypatch.setattr(
        ipxe_routes, "save_menu", lambda m: saved.append(m) or {"valid": True, "warnings": []}
    )
    return model, saved


def test_menu_state_reports_only_the_kaspersky_entries(api, menu):
    state_ = client.get("/api/kaspersky/display").json()["menu"]
    assert [e["name"] for e in state_["entries"]] == ["kaspersky_1"]
    assert state_["hook"] is False and state_["native_video"] is False


def test_enabling_the_script_adds_it_to_the_boot_line_and_saves(api, menu):
    model, saved = menu
    got = client.post("/api/kaspersky/display/menu", json={"hook": True}).json()["menu"]
    assert got["hook"] is True
    cmdline = model.entries[0].cmdline
    assert (
        "live-config.hooks=http://${server_ip}:${port}/ipxe/krd-display.sh?mac=${net0/mac}"
        in cmdline
    )
    assert "nomodeset" in cmdline  # untouched
    assert len(saved) == 1
    assert model.entries[1].cmdline == "boot=casper nomodeset"  # other entries are left alone


def test_turning_it_on_twice_does_not_repeat_it_and_off_removes_it(api, menu):
    model, _ = menu
    client.post("/api/kaspersky/display/menu", json={"hook": True})
    client.post("/api/kaspersky/display/menu", json={"hook": True})
    assert model.entries[0].cmdline.count("live-config.hooks=") == 1
    client.post("/api/kaspersky/display/menu", json={"hook": False})
    assert "live-config.hooks" not in model.entries[0].cmdline
    assert model.entries[0].cmdline.startswith("boot=live components")


def test_native_video_removes_nomodeset_and_safe_puts_it_back(api, menu):
    model, _ = menu
    got = client.post("/api/kaspersky/display/menu", json={"native_video": True}).json()["menu"]
    assert got["native_video"] is True and "nomodeset" not in model.entries[0].cmdline
    client.post("/api/kaspersky/display/menu", json={"native_video": False})
    assert model.entries[0].cmdline.split().count("nomodeset") == 1


def test_a_menu_without_a_kaspersky_entry_is_a_clear_404(api, monkeypatch):
    monkeypatch.setattr(ipxe_routes, "saved_menu", lambda: None)
    assert client.post("/api/kaspersky/display/menu", json={"hook": True}).status_code == 404


def test_a_menu_that_does_not_validate_is_not_reported_as_saved(api, menu, monkeypatch):
    monkeypatch.setattr(ipxe_routes, "save_menu", lambda m: {"valid": False, "message": "bad"})
    resp = client.post("/api/kaspersky/display/menu", json={"hook": True})
    assert resp.status_code == 422 and "bad" in resp.json()["detail"]


def test_the_script_logs_what_it_was_asked_and_what_the_video_mode_is(machine):
    (machine.root / "proc").mkdir()
    (machine.root / "proc" / "cmdline").write_text("boot=live nomodeset BOOTIF=01-x\n")
    machine.panel("1920x1080", 344)
    env = {"IPXE_STATION_PROC": str(machine.root / "proc")}
    machine.run("auto", extra_env=env)
    assert "text size requested: auto" in machine.log
    assert "video: safe mode (nomodeset)" in machine.log
    (machine.root / "proc" / "cmdline").write_text("boot=live BOOTIF=01-x\n")
    machine.run("auto", extra_env=env)
    assert "video: the kernel video driver is on" in machine.log
