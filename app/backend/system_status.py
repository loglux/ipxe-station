"""
System status monitoring for PXE Boot Station
Handles system monitoring, service status checks, and resource usage
REFACTORED: Using common utilities to eliminate repetition
"""

import os
import psutil
import socket
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# Import common utilities to eliminate repetition
from backend.utils import (
    get_file_info,
    safe_operation,
    export_status_as_json,
    get_cross_platform_path
)

# Fix for Windows compatibility
try:
    import pwd
    import grp
except ImportError:
    pwd = None
    grp = None


class ServiceStatus(Enum):
    """Service status states"""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class DiskUsage:
    """Disk usage information"""
    path: str
    total: int
    used: int
    free: int
    percent: float

    @property
    def total_gb(self) -> float:
        """Total space in GB"""
        return self.total / (1024 ** 3)

    @property
    def used_gb(self) -> float:
        """Used space in GB"""
        return self.used / (1024 ** 3)

    @property
    def free_gb(self) -> float:
        """Free space in GB"""
        return self.free / (1024 ** 3)


@dataclass
class NetworkInterface:
    """Network interface information"""
    name: str
    ip_address: Optional[str] = None
    netmask: Optional[str] = None
    broadcast: Optional[str] = None
    mac_address: Optional[str] = None
    is_up: bool = False
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0


@dataclass
class ServiceInfo:
    """Service information"""
    name: str
    status: ServiceStatus
    pid: Optional[int] = None
    port: Optional[int] = None
    protocol: str = "tcp"
    description: str = ""
    error_message: str = ""
    uptime: Optional[timedelta] = None


@dataclass
class SystemInfo:
    """Complete system information"""
    hostname: str
    platform: str
    architecture: str
    cpu_count: int
    memory_total: int
    memory_available: int
    memory_percent: float
    cpu_percent: float
    uptime: timedelta
    load_average: Optional[Tuple[float, float, float]] = None
    boot_time: datetime = field(default_factory=datetime.now)


class ServiceChecker:
    """Service status checking utilities"""

    @staticmethod
    def check_port_listening(port: int, protocol: str = "tcp", host: str = "127.0.0.1") -> bool:
        """Check if a port is listening"""
        try:
            if protocol.lower() == "tcp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()

            return result == 0
        except Exception:
            return False

    @staticmethod
    def check_process_by_name(process_name: str) -> Tuple[bool, List[int]]:
        """Check if process is running by name"""
        try:
            pids = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if process_name.lower() in proc.info['name'].lower():
                        pids.append(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return len(pids) > 0, pids
        except Exception:
            return False, []

    @staticmethod
    def check_process_by_port(port: int, protocol: str = "tcp") -> Tuple[bool, Optional[int]]:
        """Check process listening on specific port"""
        try:
            connections = psutil.net_connections()
            for conn in connections:
                if (hasattr(conn, 'laddr') and conn.laddr and
                        conn.laddr.port == port and
                        conn.type == getattr(socket, f"SOCK_{protocol.upper()}")):
                    return True, conn.pid
            return False, None
        except Exception:
            return False, None

    @staticmethod
    def get_process_uptime(pid: int) -> Optional[timedelta]:
        """Get process uptime"""
        try:
            proc = psutil.Process(pid)
            create_time = datetime.fromtimestamp(proc.create_time())
            return datetime.now() - create_time
        except Exception:
            return None

    @staticmethod
    @safe_operation("Systemd service check", return_tuple=True)
    def check_systemd_service(service_name: str) -> Tuple[ServiceStatus, str]:
        """Check systemd service status"""
        # Check if systemctl is available
        result = subprocess.run(
            ['systemctl', '--version'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode != 0:
            return ServiceStatus.UNKNOWN, "systemctl not available"

        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True, text=True, timeout=5
        )

        status = result.stdout.strip()
        if status == "active":
            return ServiceStatus.RUNNING, "Service is active"
        elif status == "inactive":
            return ServiceStatus.STOPPED, "Service is inactive"
        elif status == "failed":
            return ServiceStatus.ERROR, "Service failed"
        else:
            return ServiceStatus.UNKNOWN, f"Unknown status: {status}"


class SystemMonitor:
    """System resource monitoring utilities"""

    @staticmethod
    @safe_operation("System information gathering")
    def get_system_info() -> SystemInfo:
        """Get comprehensive system information"""
        # Basic system info
        hostname = socket.gethostname()
        platform = os.name

        # Get architecture - cross-platform way
        try:
            import platform as plt
            architecture = plt.machine()
        except:
            architecture = 'unknown'

        # CPU and memory
        cpu_count = psutil.cpu_count() or 1
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)

        # Uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        # Load average (Unix-like systems only)
        load_avg = None
        try:
            if hasattr(os, 'getloadavg'):
                load_avg = os.getloadavg()
        except (OSError, AttributeError):
            pass

        return SystemInfo(
            hostname=hostname,
            platform=platform,
            architecture=architecture,
            cpu_count=cpu_count,
            memory_total=memory.total,
            memory_available=memory.available,
            memory_percent=memory.percent,
            cpu_percent=cpu_percent,
            uptime=uptime,
            load_average=load_avg,
            boot_time=boot_time
        )

    @staticmethod
    def get_disk_usage(paths: List[str] = None) -> List[DiskUsage]:
        """Get disk usage for specified paths"""
        if paths is None:
            # Default paths - cross-platform
            if os.name == 'nt':  # Windows
                paths = ["C:\\", "D:\\"]
            else:  # Unix-like
                paths = ["/", "/srv", "/tmp"]

        disk_usage = []

        for path in paths:
            try:
                if not Path(path).exists():
                    continue

                usage = psutil.disk_usage(path)
                disk_usage.append(DiskUsage(
                    path=path,
                    total=usage.total,
                    used=usage.used,
                    free=usage.free,
                    percent=(usage.used / usage.total) * 100 if usage.total > 0 else 0
                ))
            except Exception:
                continue

        return disk_usage

    @staticmethod
    def get_network_interfaces() -> List[NetworkInterface]:
        """Get network interface information"""
        interfaces = []

        try:
            # Get network interface addresses
            addresses = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            # Get I/O counters (may not be available on all systems)
            io_counters = {}
            try:
                io_counters = psutil.net_io_counters(pernic=True)
            except:
                pass

            for interface_name, addr_list in addresses.items():
                # Skip loopback interface
                if interface_name.startswith(('lo', 'Loopback')):
                    continue

                interface = NetworkInterface(name=interface_name)

                # Get IP addresses
                for addr in addr_list:
                    if addr.family == socket.AF_INET:  # IPv4
                        interface.ip_address = addr.address
                        interface.netmask = addr.netmask
                        interface.broadcast = addr.broadcast
                    elif hasattr(psutil, 'AF_LINK') and addr.family == psutil.AF_LINK:  # MAC address (Unix)
                        interface.mac_address = addr.address
                    elif os.name == 'nt' and addr.family == socket.AF_INET:  # Windows MAC handling
                        # On Windows, MAC address is usually in a different field
                        pass

                # Get interface status
                if interface_name in stats:
                    interface.is_up = stats[interface_name].isup

                # Get I/O counters if available
                if interface_name in io_counters:
                    io = io_counters[interface_name]
                    interface.bytes_sent = io.bytes_sent
                    interface.bytes_recv = io.bytes_recv
                    interface.packets_sent = io.packets_sent
                    interface.packets_recv = io.packets_recv

                interfaces.append(interface)

        except Exception:
            pass

        return interfaces


class PXEServiceMonitor:
    """PXE-specific service monitoring"""

    def __init__(self):
        self.service_checker = ServiceChecker()
        self.system_monitor = SystemMonitor()

    @safe_operation("TFTP service check")
    def check_tftp_service(self) -> ServiceInfo:
        """Check TFTP service status"""
        service = ServiceInfo(
            name="TFTP Server",
            status=ServiceStatus.UNKNOWN,
            port=69,
            protocol="udp",
            description="Trivial File Transfer Protocol server"
        )

        # Check if port 69 is listening
        is_listening = self.service_checker.check_port_listening(69, "udp")

        if is_listening:
            # Try to find process on port 69
            is_running, pid = self.service_checker.check_process_by_port(69, "udp")
            if is_running and pid:
                service.status = ServiceStatus.RUNNING
                service.pid = pid
                service.uptime = self.service_checker.get_process_uptime(pid)
            else:
                service.status = ServiceStatus.RUNNING
                service.error_message = "TFTP service active"
        else:
            service.status = ServiceStatus.STOPPED
            service.error_message = "Port 69/UDP not listening"

        return service

    @safe_operation("HTTP service check")
    def check_http_service(self, port: int = 8000) -> ServiceInfo:
        """Check HTTP service status (FastAPI + Gradio)"""
        service = ServiceInfo(
            name="HTTP Server",
            status=ServiceStatus.UNKNOWN,
            port=port,
            protocol="tcp",
            description="HTTP server for PXE boot files"
        )

        # Check if port is listening
        is_listening = self.service_checker.check_port_listening(port, "tcp")

        if is_listening:
            # Try to find process on port
            is_running, pid = self.service_checker.check_process_by_port(port, "tcp")
            if is_running and pid:
                service.status = ServiceStatus.RUNNING
                service.pid = pid
                service.uptime = self.service_checker.get_process_uptime(pid)
                service.error_message = "FastAPI + Gradio running"
            else:
                service.status = ServiceStatus.RUNNING
                service.error_message = "HTTP service active"
        else:
            service.status = ServiceStatus.STOPPED
            service.error_message = f"Port {port}/TCP not listening"

        return service

    @safe_operation("Gradio service check")
    def check_gradio_service(self, port: int = 8000) -> ServiceInfo:
        """Check Gradio UI service status (part of FastAPI)"""
        service = ServiceInfo(
            name="Gradio UI",
            status=ServiceStatus.UNKNOWN,
            port=port,
            protocol="tcp",
            description="Gradio web interface"
        )

        # Check if HTTP service is running first
        http_listening = self.service_checker.check_port_listening(port, "tcp")

        if http_listening:
            # Try to test Gradio endpoint specifically
            try:
                import requests
                response = requests.get(f"http://localhost:{port}/pxe-station", timeout=2)
                if response.status_code in [200, 302]:  # 302 for redirects
                    service.status = ServiceStatus.RUNNING
                    service.error_message = "Gradio UI accessible"
                else:
                    service.status = ServiceStatus.ERROR
                    service.error_message = f"Gradio endpoint returned HTTP {response.status_code}"
            except ImportError:
                # Fallback if requests not available
                service.status = ServiceStatus.RUNNING
                service.error_message = "HTTP service running (Gradio likely available)"
            except Exception as e:
                service.status = ServiceStatus.ERROR
                service.error_message = f"Gradio endpoint test failed: {str(e)}"
        else:
            service.status = ServiceStatus.STOPPED
            service.error_message = f"HTTP service not running on port {port}"

        return service

    @safe_operation("DHCP service check")
    def check_dhcp_service(self) -> ServiceInfo:
        """Check DHCP service status (external)"""
        service = ServiceInfo(
            name="DHCP Server",
            status=ServiceStatus.UNKNOWN,
            port=67,
            protocol="udp",
            description="DHCP server (external)"
        )

        # Only check systemd services on Unix-like systems
        if os.name != 'nt':
            # Check common DHCP services
            dhcp_services = ["isc-dhcp-server", "dhcpd", "dnsmasq"]

            for service_name in dhcp_services:
                status, message = self.service_checker.check_systemd_service(service_name)
                if status == ServiceStatus.RUNNING:
                    service.status = ServiceStatus.RUNNING
                    service.error_message = f"{service_name} is running"
                    break
                elif status == ServiceStatus.ERROR:
                    service.status = ServiceStatus.ERROR
                    service.error_message = f"{service_name} failed: {message}"
                    break

        if service.status == ServiceStatus.UNKNOWN:
            # Check if port 67 is listening
            is_listening = self.service_checker.check_port_listening(67, "udp")
            if is_listening:
                service.status = ServiceStatus.RUNNING
                service.error_message = "DHCP port is active (unknown service)"
            else:
                service.status = ServiceStatus.STOPPED
                service.error_message = "No DHCP service detected"

        return service


class FileSystemMonitor:
    """File system monitoring for PXE files"""

    @staticmethod
    def check_pxe_files() -> Dict[str, Dict[str, Any]]:
        """Check status of PXE boot files with support for versioned Ubuntu structure"""
        # Cross-platform file paths using common utility
        base_tftp = get_cross_platform_path("/srv/tftp")
        base_http = get_cross_platform_path("/srv/http")
        base_ipxe = get_cross_platform_path("/srv/ipxe")

        file_status = {}

        # Check iPXE boot files
        ipxe_files = {
            "iPXE BIOS": f"{base_tftp}/undionly.kpxe",
            "iPXE UEFI": f"{base_tftp}/ipxe.efi",
            "iPXE Menu": f"{base_ipxe}/boot.ipxe"
        }

        # Process iPXE files using common utility
        for name, path in ipxe_files.items():
            file_status[name] = get_file_info(path)

        # Check Ubuntu files - scan for versioned directories
        ubuntu_base = Path(base_http)
        ubuntu_found = False

        if ubuntu_base.exists():
            # Look for ubuntu-* directories
            ubuntu_dirs = [d for d in ubuntu_base.iterdir()
                           if d.is_dir() and d.name.startswith('ubuntu-')]

            if ubuntu_dirs:
                # Found versioned Ubuntu directories
                latest_version = None
                latest_kernel = None
                latest_initrd = None

                for ubuntu_dir in sorted(ubuntu_dirs, reverse=True):  # Sort to get latest first
                    kernel_path = ubuntu_dir / "vmlinuz"
                    initrd_path = ubuntu_dir / "initrd"

                    if kernel_path.exists() and initrd_path.exists():
                        if latest_version is None:  # First (latest) valid version found
                            latest_version = ubuntu_dir.name
                            latest_kernel = str(kernel_path)
                            latest_initrd = str(initrd_path)
                            ubuntu_found = True

                        # Add version-specific entries using common utility
                        version = ubuntu_dir.name.replace('ubuntu-', '')
                        file_status[f"Ubuntu {version} Kernel"] = get_file_info(str(kernel_path))
                        file_status[f"Ubuntu {version} Initrd"] = get_file_info(str(initrd_path))

                # Add latest as primary entries for compatibility
                if ubuntu_found:
                    file_status["Ubuntu Kernel"] = get_file_info(latest_kernel)
                    file_status["Ubuntu Initrd"] = get_file_info(latest_initrd)
            else:
                # Fallback to old single ubuntu directory
                old_ubuntu_dir = ubuntu_base / "ubuntu"
                if old_ubuntu_dir.exists():
                    kernel_path = old_ubuntu_dir / "vmlinuz"
                    initrd_path = old_ubuntu_dir / "initrd"
                    file_status["Ubuntu Kernel"] = get_file_info(str(kernel_path))
                    file_status["Ubuntu Initrd"] = get_file_info(str(initrd_path))
                    ubuntu_found = kernel_path.exists() and initrd_path.exists()

        # If no Ubuntu files found, add missing entries
        if not ubuntu_found:
            file_status["Ubuntu Kernel"] = {
                "path": f"{base_http}/ubuntu*/vmlinuz",
                "exists": False,
                "size": 0,
                "size_human": "0 B",
                "modified": None,
                "readable": False
            }
            file_status["Ubuntu Initrd"] = {
                "path": f"{base_http}/ubuntu*/initrd",
                "exists": False,
                "size": 0,
                "size_human": "0 B",
                "modified": None,
                "readable": False
            }

        # Check for Ubuntu ISO (optional)
        iso_found = False
        if ubuntu_base.exists():
            iso_patterns = ["*.iso"]
            for pattern in iso_patterns:
                iso_files = list(ubuntu_base.rglob(pattern))
                if iso_files:
                    # Use first found ISO and use common utility
                    iso_file = iso_files[0]
                    file_status["Ubuntu ISO"] = get_file_info(str(iso_file))
                    iso_found = True
                    break

        if not iso_found:
            file_status["Ubuntu ISO"] = {
                "path": f"{base_http}/ubuntu*/ubuntu-*.iso",
                "exists": False,
                "size": 0,
                "size_human": "0 B",
                "modified": None,
                "readable": False
            }

        return file_status


class SystemStatusManager:
    """Main system status management class"""

    def __init__(self):
        self.pxe_monitor = PXEServiceMonitor()
        self.system_monitor = SystemMonitor()
        self.filesystem_monitor = FileSystemMonitor()

    @safe_operation("Complete status gathering")
    def get_complete_status(self) -> Dict[str, Any]:
        """Get complete system status"""
        # System information
        system_info = self.system_monitor.get_system_info()

        # Service status - updated to use correct ports
        services = {
            "tftp": self.pxe_monitor.check_tftp_service(),
            "http": self.pxe_monitor.check_http_service(8000),  # Fixed: internal container port
            "gradio": self.pxe_monitor.check_gradio_service(8000),  # Fixed: same as HTTP
            "dhcp": self.pxe_monitor.check_dhcp_service()
        }

        # Disk usage
        disk_usage = self.system_monitor.get_disk_usage()

        # Network interfaces
        network_interfaces = self.system_monitor.get_network_interfaces()

        # PXE files status - now supports versioned Ubuntu
        pxe_files = self.filesystem_monitor.check_pxe_files()

        # Overall health score
        health_score = self._calculate_health_score(services, pxe_files, system_info)

        return {
            "timestamp": datetime.now(),
            "system": {
                "hostname": system_info.hostname,
                "platform": system_info.platform,
                "architecture": system_info.architecture,
                "cpu_count": system_info.cpu_count,
                "cpu_percent": system_info.cpu_percent,
                "memory_total_gb": system_info.memory_total / (1024 ** 3),
                "memory_available_gb": system_info.memory_available / (1024 ** 3),
                "memory_percent": system_info.memory_percent,
                "uptime": str(system_info.uptime),
                "load_average": system_info.load_average,
                "boot_time": system_info.boot_time
            },
            "services": {
                name: {
                    "status": service.status.value,
                    "pid": service.pid,
                    "port": service.port,
                    "protocol": service.protocol,
                    "description": service.description,
                    "error_message": service.error_message,
                    "uptime": str(service.uptime) if service.uptime else None
                }
                for name, service in services.items()
            },
            "disk_usage": [
                {
                    "path": disk.path,
                    "total_gb": disk.total_gb,
                    "used_gb": disk.used_gb,
                    "free_gb": disk.free_gb,
                    "percent": disk.percent
                }
                for disk in disk_usage
            ],
            "network_interfaces": [
                {
                    "name": iface.name,
                    "ip_address": iface.ip_address,
                    "netmask": iface.netmask,
                    "mac_address": iface.mac_address,
                    "is_up": iface.is_up,
                    "bytes_sent_mb": iface.bytes_sent / (1024 ** 2),
                    "bytes_recv_mb": iface.bytes_recv / (1024 ** 2)
                }
                for iface in network_interfaces
            ],
            "pxe_files": pxe_files,
            "health_score": health_score,
            "recommendations": self._generate_recommendations(services, pxe_files, system_info)
        }

    def _calculate_health_score(self, services: Dict[str, ServiceInfo],
                                pxe_files: Dict[str, Dict[str, Any]],
                                system_info: SystemInfo) -> int:
        """Calculate overall system health score (0-100)"""
        score = 100

        # Service penalties
        for service in services.values():
            if service.status == ServiceStatus.STOPPED:
                score -= 15
            elif service.status == ServiceStatus.ERROR:
                score -= 20
            elif service.status == ServiceStatus.UNKNOWN:
                score -= 10

        # File penalties - check for ANY Ubuntu version
        critical_files = ["iPXE BIOS", "iPXE Menu"]
        for file_name in critical_files:
            if file_name in pxe_files and not pxe_files[file_name]["exists"]:
                score -= 15

        # Check if any Ubuntu kernel/initrd exists (any version)
        ubuntu_kernel_exists = any(
            "Ubuntu" in name and "Kernel" in name and pxe_files[name]["exists"]
            for name in pxe_files
        )
        ubuntu_initrd_exists = any(
            "Ubuntu" in name and "Initrd" in name and pxe_files[name]["exists"]
            for name in pxe_files
        )

        if not ubuntu_kernel_exists:
            score -= 10
        if not ubuntu_initrd_exists:
            score -= 10

        # System resource penalties
        if system_info.memory_percent > 90:
            score -= 10
        elif system_info.memory_percent > 80:
            score -= 5

        if system_info.cpu_percent > 90:
            score -= 10
        elif system_info.cpu_percent > 80:
            score -= 5

        return max(0, score)

    def _generate_recommendations(self, services: Dict[str, ServiceInfo],
                                  pxe_files: Dict[str, Dict[str, Any]],
                                  system_info: SystemInfo) -> List[str]:
        """Generate system recommendations"""
        recommendations = []

        # Service recommendations
        if services["tftp"].status != ServiceStatus.RUNNING:
            recommendations.append("🔧 Start TFTP server for PXE boot functionality")

        if services["http"].status != ServiceStatus.RUNNING:
            recommendations.append("🔧 Start HTTP server for serving boot files")

        if services["gradio"].status != ServiceStatus.RUNNING:
            recommendations.append("🔧 Check Gradio web interface accessibility")

        if services["dhcp"].status != ServiceStatus.RUNNING:
            recommendations.append("⚠️ Configure DHCP server with PXE options")

        # File recommendations - check for missing critical files
        critical_files = ["iPXE BIOS", "iPXE Menu"]
        missing_files = [name for name in critical_files
                         if name in pxe_files and not pxe_files[name]["exists"]]

        if missing_files:
            recommendations.append(f"📁 Install missing files: {', '.join(missing_files)}")

        # Check Ubuntu files - any version
        ubuntu_versions_found = [
            name.replace("Ubuntu ", "").replace(" Kernel", "")
            for name in pxe_files
            if "Ubuntu" in name and "Kernel" in name and pxe_files[name]["exists"]
        ]

        if not ubuntu_versions_found:
            recommendations.append("🐧 Download Ubuntu boot files (kernel + initrd)")
        else:
            recommendations.append(f"✅ Ubuntu versions available: {', '.join(ubuntu_versions_found)}")

        # System recommendations
        if system_info.memory_percent > 85:
            recommendations.append("💾 High memory usage detected - consider freeing memory")

        if system_info.cpu_percent > 85:
            recommendations.append("⚡ High CPU usage detected - system may be under load")

        # Add positive recommendations
        if len([r for r in recommendations if not r.startswith("✅")]) == 0:
            recommendations.append("✅ System is running optimally!")

        return recommendations

    def export_status_json(self) -> str:
        """Export complete status as JSON using common utility"""
        status = self.get_complete_status()
        return export_status_as_json(status, pretty=True)


# Helper functions using common utilities
def _calculate_dhcp_range(subnet: str, netmask: str) -> str:
    """Calculate DHCP range from subnet and netmask"""
    try:
        import ipaddress
        network = ipaddress.IPv4Network(f"{subnet}/{netmask}", strict=False)
        # Use middle 50% of the network for DHCP range
        hosts = list(network.hosts())
        if len(hosts) < 4:
            # Very small network, use all available hosts except first and last
            start_ip = str(hosts[0])
            end_ip = str(hosts[-1])
        else:
            # Skip first 25% and last 25% of addresses
            start_idx = len(hosts) // 4
            end_idx = len(hosts) - (len(hosts) // 4)
            start_ip = str(hosts[start_idx])
            end_ip = str(hosts[end_idx - 1])

        return f"{start_ip} {end_ip}"
    except Exception:
        return "192.168.1.100 192.168.1.200"  # Fallback range


def _netmask_to_cidr(netmask: str) -> int:
    """Convert netmask to CIDR notation"""
    try:
        import ipaddress
        return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    except Exception:
        return 24  # Default /24


def _seconds_to_time(seconds: int) -> str:
    """Convert seconds to time format for MikroTik"""
    if seconds >= 86400:  # days
        days = seconds // 86400
        return f"{days}d"
    elif seconds >= 3600:  # hours
        hours = seconds // 3600
        return f"{hours}h"
    elif seconds >= 60:  # minutes
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        return f"{seconds}s"


# Convenience functions for backward compatibility
def get_system_status() -> Dict[str, Any]:
    """Get system status (legacy function)"""
    manager = SystemStatusManager()
    return manager.get_complete_status()


def check_services() -> Dict[str, ServiceInfo]:
    """Check all services (legacy function)"""
    monitor = PXEServiceMonitor()
    return {
        "tftp": monitor.check_tftp_service(),
        "http": monitor.check_http_service(8000),  # Fixed port
        "gradio": monitor.check_gradio_service(8000),  # Fixed port
        "dhcp": monitor.check_dhcp_service()
    }


def get_disk_usage() -> List[DiskUsage]:
    """Get disk usage (legacy function)"""
    return SystemMonitor.get_disk_usage()