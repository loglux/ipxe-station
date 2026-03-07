"""Tests for system_status module."""

import os
import socket
from datetime import timedelta

import psutil

from app.backend.system_status import (
    DiskUsage,
    NetworkInterface,
    ServiceChecker,
    ServiceInfo,
    ServiceStatus,
    SystemInfo,
    SystemMonitor,
)


class TestServiceStatus:
    def test_enum_values(self):
        assert ServiceStatus.RUNNING.value == "running"
        assert ServiceStatus.STOPPED.value == "stopped"
        assert ServiceStatus.ERROR.value == "error"
        assert ServiceStatus.UNKNOWN.value == "unknown"


class TestDiskUsage:
    def setup_method(self):
        # 10 GiB total, 4 GiB used, 6 GiB free
        self.disk = DiskUsage(
            path="/srv",
            total=10 * 1024**3,
            used=4 * 1024**3,
            free=6 * 1024**3,
            percent=40.0,
        )

    def test_total_gb(self):
        assert abs(self.disk.total_gb - 10.0) < 0.01

    def test_used_gb(self):
        assert abs(self.disk.used_gb - 4.0) < 0.01

    def test_free_gb(self):
        assert abs(self.disk.free_gb - 6.0) < 0.01

    def test_path_stored(self):
        assert self.disk.path == "/srv"

    def test_percent_stored(self):
        assert self.disk.percent == 40.0


class TestNetworkInterface:
    def test_defaults(self):
        iface = NetworkInterface(name="eth0")
        assert iface.name == "eth0"
        assert iface.ip_address is None
        assert iface.netmask is None
        assert iface.mac_address is None
        assert iface.is_up is False
        assert iface.bytes_sent == 0
        assert iface.bytes_recv == 0


class TestServiceInfo:
    def test_defaults(self):
        info = ServiceInfo(name="tftp", status=ServiceStatus.RUNNING)
        assert info.name == "tftp"
        assert info.status == ServiceStatus.RUNNING
        assert info.pid is None
        assert info.port is None
        assert info.protocol == "tcp"


class TestSystemInfo:
    def test_construction(self):

        info = SystemInfo(
            hostname="test-host",
            platform="linux",
            architecture="x86_64",
            cpu_count=4,
            memory_total=8 * 1024**3,
            memory_available=4 * 1024**3,
            memory_percent=50.0,
            cpu_percent=25.0,
            uptime=timedelta(hours=5),
        )
        assert info.hostname == "test-host"
        assert info.cpu_count == 4
        assert info.memory_percent == 50.0


class TestServiceCheckerPortListening:
    def test_closed_port_returns_false(self):
        # Port 1 is almost certainly not listening
        result = ServiceChecker.check_port_listening(1, protocol="tcp")
        assert result is False

    def test_open_port_returns_true(self):
        # Start a real listening socket on a random port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            assert ServiceChecker.check_port_listening(port, protocol="tcp") is True

    def test_invalid_host_returns_false(self):
        result = ServiceChecker.check_port_listening(80, host="256.256.256.256")
        assert result is False


class TestServiceCheckerProcessByName:
    def test_nonexistent_process_returns_false(self):
        found, pids = ServiceChecker.check_process_by_name("__nonexistent_process_xyz__")
        assert found is False
        assert pids == []

    def test_existing_process(self):
        # Use the current interpreter process name to avoid env-specific hardcoding.
        current_name = psutil.Process(os.getpid()).name()
        found, pids = ServiceChecker.check_process_by_name(current_name)
        assert found is True
        assert len(pids) > 0


class TestSystemMonitorDiskUsage:
    def test_get_disk_usage_returns_list(self):
        result = SystemMonitor.get_disk_usage(["/"])
        assert isinstance(result, list)
        # Should have at least root fs
        assert len(result) >= 1

    def test_disk_usage_has_correct_fields(self):
        result = SystemMonitor.get_disk_usage(["/"])
        if result:
            disk = result[0]
            assert disk.total > 0
            assert disk.used >= 0
            assert disk.free >= 0
            assert 0 <= disk.percent <= 100

    def test_nonexistent_path_skipped(self):
        result = SystemMonitor.get_disk_usage(["/nonexistent/path/xyz"])
        assert result == []

    def test_mixed_paths(self):
        result = SystemMonitor.get_disk_usage(["/", "/nonexistent/path/xyz"])
        assert len(result) == 1
        assert result[0].path == "/"


class TestSystemMonitorNetworkInterfaces:
    def test_returns_list(self):
        interfaces = SystemMonitor.get_network_interfaces()
        assert isinstance(interfaces, list)

    def test_loopback_excluded(self):
        interfaces = SystemMonitor.get_network_interfaces()
        names = [iface.name for iface in interfaces]
        assert "lo" not in names
        assert not any(n.startswith("Loopback") for n in names)
