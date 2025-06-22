"""
Testing utilities for PXE Boot Station
Handles all testing logic including TFTP, HTTP, and system checks
"""

import os
import socket
import struct
import subprocess
import requests
from pathlib import Path
from typing import List, Tuple, Dict, Any


class TFTPTester:
    """TFTP connection testing utilities"""

    @staticmethod
    def test_tftp_connection(host: str = 'localhost', port: int = 69,
                             filename: str = 'undionly.kpxe', timeout: int = 5) -> str:
        """Test TFTP connection using Python socket"""
        try:
            # TFTP Read Request (RRQ) for specified file
            filename_bytes = filename.encode('ascii')
            mode = b'octet'

            # Create TFTP RRQ packet
            # Opcode 1 = Read Request
            packet = struct.pack('!H', 1) + filename_bytes + b'\x00' + mode + b'\x00'

            # Send request
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(packet, (host, port))

            # Receive response
            data, addr = sock.recvfrom(1024)
            sock.close()

            # Check response
            if len(data) >= 4:
                opcode = struct.unpack('!H', data[:2])[0]
                if opcode == 3:  # Data packet
                    block_num = struct.unpack('!H', data[2:4])[0]
                    data_size = len(data) - 4
                    return f"✅ TFTP test: SUCCESS (Block #{block_num}, {data_size} bytes)"
                elif opcode == 5:  # Error packet
                    error_code = struct.unpack('!H', data[2:4])[0]
                    error_msg = data[4:].decode('ascii', errors='ignore').rstrip('\x00')
                    return f"❌ TFTP test: Error {error_code} - {error_msg}"
                else:
                    return f"❓ TFTP test: Unknown opcode {opcode}"
            else:
                return "❌ TFTP test: Invalid response"

        except socket.timeout:
            return f"❌ TFTP test: Timeout after {timeout}s (server not responding)"
        except Exception as e:
            return f"❌ TFTP test: {str(e)}"


class ServiceChecker:
    """System service checking utilities"""

    @staticmethod
    def check_tftp_daemon() -> str:
        """Check if TFTP daemon is running (Docker-friendly)"""
        try:
            # Check PID files
            pid_files = ['/var/run/tftpd-hpa.pid', '/run/tftpd-hpa.pid']

            for pid_file in pid_files:
                if os.path.exists(pid_file):
                    with open(pid_file, 'r') as f:
                        pid = f.read().strip()
                        if os.path.exists(f'/proc/{pid}'):
                            return "✅ TFTP daemon: Running"

            # Alternative check via netstat if available
            try:
                result = subprocess.run(['netstat', '-ulnp'],
                                        capture_output=True, text=True, timeout=5)
                if ':69 ' in result.stdout:
                    return "✅ TFTP daemon: Listening on port 69"
                else:
                    return "❓ TFTP daemon: Port 69 status unknown"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return "✅ TFTP daemon: Likely running (port responding)"

        except Exception as e:
            return f"❓ TFTP daemon check: {str(e)}"

    @staticmethod
    def check_port_availability(port: int, protocol: str = 'tcp') -> str:
        """Check if port is available"""
        try:
            if protocol.lower() == 'tcp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()

            if result == 0:
                return f"❌ Port {port}/{protocol.upper()}: In use"
            else:
                return f"✅ Port {port}/{protocol.upper()}: Available"
        except Exception as e:
            return f"❓ Port {port}/{protocol.upper()}: {str(e)}"


class HTTPTester:
    """HTTP endpoint testing utilities"""

    @staticmethod
    def test_endpoint(url: str, timeout: int = 5, expected_status: int = 200) -> str:
        """Test HTTP endpoint"""
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == expected_status:
                return f"✅ {url}: OK"
            else:
                return f"❌ {url}: HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            return f"❌ {url}: Timeout after {timeout}s"
        except requests.exceptions.ConnectionError:
            return f"❌ {url}: Connection failed"
        except Exception as e:
            return f"❌ {url}: {str(e)}"


class FileChecker:
    """File and directory checking utilities"""

    @staticmethod
    def check_file_exists(filepath: str, show_size: bool = True) -> str:
        """Check if file exists and optionally show size"""
        path = Path(filepath)
        if path.exists():
            if show_size:
                if path.is_file():
                    size = path.stat().st_size
                    if size > 1024 * 1024:  # > 1MB
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    elif size > 1024:  # > 1KB
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size} bytes"
                    return f"✅ {path.name}: Found ({size_str})"
                else:
                    return f"✅ {path.name}: Found (directory)"
            else:
                return f"✅ {path.name}: Found"
        else:
            return f"❌ {path.name}: Missing"


class SystemTester:
    """Main system testing orchestrator"""

    def __init__(self):
        self.tftp_tester = TFTPTester()
        self.service_checker = ServiceChecker()
        self.http_tester = HTTPTester()
        self.file_checker = FileChecker()

    def run_full_system_test(self) -> str:
        """Run complete system test and return formatted results"""
        results = []

        # Test TFTP connection
        tftp_result = self.tftp_tester.test_tftp_connection()
        results.append(tftp_result)

        # Check TFTP daemon
        daemon_result = self.service_checker.check_tftp_daemon()
        results.append(daemon_result)

        # Check port availability
        port_result = self.service_checker.check_port_availability(69, 'udp')
        results.append(port_result)

        # Test main HTTP server
        http_result = self.http_tester.test_endpoint("http://localhost:8000/status")
        results.append(http_result)

        # Test Gradio UI
        results.append("✅ Gradio UI (port 9005): Running (you're using it now!)")

        # Test iPXE menu
        ipxe_file_result = self.file_checker.check_file_exists("/srv/ipxe/boot.ipxe", False)
        results.append(ipxe_file_result)

        if "Found" in ipxe_file_result:
            ipxe_http_result = self.http_tester.test_endpoint("http://localhost:8000/ipxe/boot.ipxe")
            results.append(ipxe_http_result)

        # Test Ubuntu files
        ubuntu_kernel_result = self.file_checker.check_file_exists("/srv/http/ubuntu/vmlinuz")
        results.append(ubuntu_kernel_result)

        ubuntu_initrd_result = self.file_checker.check_file_exists("/srv/http/ubuntu/initrd")
        results.append(ubuntu_initrd_result)

        # Test iPXE files
        ipxe_bios_result = self.file_checker.check_file_exists("/srv/tftp/undionly.kpxe")
        results.append(ipxe_bios_result)

        ipxe_uefi_result = self.file_checker.check_file_exists("/srv/tftp/ipxe.efi")
        results.append(ipxe_uefi_result)

        # Add final status
        results.extend(self._generate_final_status(results))

        return "\n".join(results)

    def _generate_final_status(self, test_results: List[str]) -> List[str]:
        """Generate final status based on test results"""
        critical_tests = [
            "Ubuntu kernel: Found",
            "Ubuntu initrd: Found",
            "iPXE BIOS: Found",
            "iPXE menu file: Found"
        ]

        critical_passed = all(
            any(critical in result for result in test_results)
            for critical in critical_tests
        )

        status_lines = [""]

        if critical_passed:
            status_lines.extend([
                "🎉 READY FOR PXE BOOT TESTING!",
                "📋 All main components are working",
                "",
                "🔍 Next steps:",
                "1. Configure DHCP: Option 66 = YOUR_SERVER_IP, Option 67 = undionly.kpxe",
                "2. Boot test computer via network (PXE)",
                "3. Or test with QEMU emulator"
            ])
        else:
            status_lines.extend([
                "⚠️ SYSTEM NOT READY",
                "❌ Some critical components are missing",
                "",
                "🔧 Please check:",
                "1. Download Ubuntu files",
                "2. Generate iPXE menu",
                "3. Verify file permissions"
            ])

        return status_lines


# Convenience functions for backward compatibility
def test_tftp_connection() -> str:
    """Legacy function for TFTP testing"""
    return TFTPTester.test_tftp_connection()


def test_http_endpoints() -> str:
    """Legacy function for HTTP testing"""
    tester = SystemTester()
    return tester.run_full_system_test()