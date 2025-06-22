"""
System status monitoring for PXE Boot Station
Handles system monitoring, service status checks, and resource usage
"""

import os
import psutil
import socket
import subprocess
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


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
            for conn in psutil.net_connections():
                if (conn.laddr.port == port and
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
    def check_systemd_service(service_name: str) -> Tuple[ServiceStatus, str]:
        """Check systemd service status"""
        try:
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

        except subprocess.TimeoutExpired:
            return ServiceStatus.UNKNOWN, "Timeout checking service"
        except FileNotFoundError:
            return ServiceStatus.UNKNOWN, "systemctl not found"
        except Exception as e:
            return ServiceStatus.ERROR, f"Error: {str(e)}"


class SystemMonitor:
    """System resource monitoring utilities"""

    @staticmethod
    def get_system_info() -> SystemInfo:
        """Get comprehensive system information"""
        try:
            # Basic system info
            hostname = socket.gethostname()
            platform = psutil.os.name
            architecture = os.uname().machine if hasattr(os, 'uname') else 'unknown'

            # CPU and memory
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)

            # Uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time

            # Load average (Unix-like systems)
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

        except Exception as e:
            # Return minimal info on error
            return SystemInfo(
                hostname="unknown",
                platform="unknown",
                architecture="unknown",
                cpu_count=1,
                memory_total=0,
                memory_available=0,
                memory_percent=0.0,
                cpu_percent=0.0,
                uptime=timedelta(0)
            )

    @staticmethod
    def get_disk_usage(paths: List[str] = None) -> List[DiskUsage]:
        """Get disk usage for specified paths"""
        if paths is None:
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
            io_counters = psutil.net_io_counters(pernic=True)

            for interface_name, addr_list in addresses.items():
                # Skip loopback interface
                if interface_name.startswith('lo'):
                    continue

                interface = NetworkInterface(name=interface_name)

                # Get IP addresses
                for addr in addr_list:
                    if addr.family == socket.AF_INET:  # IPv4
                        interface.ip_address = addr.address
                        interface.netmask = addr.netmask
                        interface.broadcast = addr.broadcast
                    elif addr.family == psutil.AF_LINK:  # MAC address
                        interface.mac_address = addr.address

                # Get interface status
                if interface_name in stats:
                    interface.is_up = stats[interface_name].isup

                # Get I/O counters
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
                service.error_message = "Port listening but process not found"
        else:
            service.status = ServiceStatus.STOPPED
            service.error_message = "Port 69/UDP not listening"

        return service

    def check_http_service(self, port: int = 8000) -> ServiceInfo:
        """Check HTTP service status"""
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
            else:
                service.status = ServiceStatus.RUNNING
                service.error_message = "Port listening but process not found"
        else:
            service.status = ServiceStatus.STOPPED
            service.error_message = f"Port {port}/TCP not listening"

        return service

    def check_gradio_service(self, port: int = 9005) -> ServiceInfo:
        """Check Gradio UI service status"""
        service = ServiceInfo(
            name="Gradio UI",
            status=ServiceStatus.UNKNOWN,
            port=port,
            protocol="tcp",
            description="Gradio web interface"
        )

        # Check if port is listening
        is_listening = self.service_checker.check_port_listening(port, "tcp")

        if is_listening:
            service.status = ServiceStatus.RUNNING
            service.error_message = "Currently running (you're using it now!)"
        else:
            service.status = ServiceStatus.STOPPED
            service.error_message = f"Port {port}/TCP not listening"

        return service

    def check_dhcp_service(self) -> ServiceInfo:
        """Check DHCP service status (external)"""
        service = ServiceInfo(
            name="DHCP Server",
            status=ServiceStatus.UNKNOWN,
            port=67,
            protocol="udp",
            description="DHCP server (external)"
        )

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
        """Check status of PXE boot files"""
        files_to_check = {
            "iPXE BIOS": "/srv/tftp/undionly.kpxe",
            "iPXE UEFI": "/srv/tftp/ipxe.efi",
            "iPXE Menu": "/srv/ipxe/boot.ipxe",
            "Ubuntu Kernel": "/srv/http/ubuntu/vmlinuz",
            "Ubuntu Initrd": "/srv/http/ubuntu/initrd",
            "Ubuntu ISO": "/srv/http/ubuntu/ubuntu-22.04-live-server-amd64.iso"
        }

        file_status = {}

        for name, path in files_to_check.items():
            file_path = Path(path)
            status = {
                "path": path,
                "exists": file_path.exists(),
                "size": 0,
                "size_human": "0 B",
                "modified": None,
                "readable": False
            }

            if file_path.exists():
                try:
                    stat = file_path.stat()
                    status["size"] = stat.st_size
                    status["size_human"] = FileSystemMonitor._format_size(stat.st_size)
                    status["modified"] = datetime.fromtimestamp(stat.st_mtime)
                    status["readable"] = os.access(path, os.R_OK)
                except Exception:
                    pass

            file_status[name] = status

        return file_status

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f} {size_names[i]}"


class SystemStatusManager:
    """Main system status management class"""

    def __init__(self):
        self.pxe_monitor = PXEServiceMonitor()
        self.system_monitor = SystemMonitor()
        self.filesystem_monitor = FileSystemMonitor()

    def get_complete_status(self) -> Dict[str, Any]:
        """Get complete system status"""
        # System information
        system_info = self.system_monitor.get_system_info()

        # Service status
        services = {
            "tftp": self.pxe_monitor.check_tftp_service(),
            "http": self.pxe_monitor.check_http_service(),
            "gradio": self.pxe_monitor.check_gradio_service(),
            "dhcp": self.pxe_monitor.check_dhcp_service()
        }

        # Disk usage
        disk_usage = self.system_monitor.get_disk_usage()

        # Network interfaces
        network_interfaces = self.system_monitor.get_network_interfaces()

        # PXE files status
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

        # File penalties
        critical_files = ["iPXE BIOS", "iPXE Menu", "Ubuntu Kernel", "Ubuntu Initrd"]
        for file_name in critical_files:
            if file_name in pxe_files and not pxe_files[file_name]["exists"]:
                score -= 15

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

        if services["dhcp"].status != ServiceStatus.RUNNING:
            recommendations.append("⚠️ Configure DHCP server with PXE options")

        # File recommendations
        critical_files = ["iPXE BIOS", "iPXE Menu", "Ubuntu Kernel", "Ubuntu Initrd"]
        missing_files = [name for name in critical_files
                         if name in pxe_files and not pxe_files[name]["exists"]]

        if missing_files:
            recommendations.append(f"📁 Install missing files: {', '.join(missing_files)}")

        # System recommendations
        if system_info.memory_percent > 85:
            recommendations.append("💾 High memory usage detected - consider freeing memory")

        if system_info.cpu_percent > 85:
            recommendations.append("⚡ High CPU usage detected - system may be under load")

        # Add positive recommendations
        if not recommendations:
            recommendations.append("✅ System is running optimally!")

        return recommendations

    def export_status_json(self) -> str:
        """Export complete status as JSON"""
        status = self.get_complete_status()

        # Convert datetime objects to strings for JSON serialization
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, timedelta):
                return str(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(status, indent=2, default=json_serializer)


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
        "http": monitor.check_http_service(),
        "gradio": monitor.check_gradio_service(),
        "dhcp": monitor.check_dhcp_service()
    }


def get_disk_usage() -> List[DiskUsage]:
    """Get disk usage (legacy function)"""
    return SystemMonitor.get_disk_usage()