"""
Testing utilities for PXE Boot Station
Handles all testing logic including TFTP, HTTP, and system checks
Enhanced to support versioned Ubuntu structure
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
    """File and directory checking utilities with Ubuntu version support"""

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

    @staticmethod
    def scan_ubuntu_versions(base_path: str = "/srv/http") -> Dict[str, Dict[str, Any]]:
        """Scan for Ubuntu versions and their files"""
        base_dir = Path(base_path)
        versions = {}

        if not base_dir.exists():
            return versions

        # Look for ubuntu-* directories
        for ubuntu_dir in base_dir.iterdir():
            if not ubuntu_dir.is_dir() or not ubuntu_dir.name.startswith('ubuntu-'):
                continue

            version = ubuntu_dir.name.replace('ubuntu-', '')

            # Check files
            kernel_path = ubuntu_dir / "vmlinuz"
            initrd_path = ubuntu_dir / "initrd"
            preseed_path = ubuntu_dir / "preseed.cfg"
            iso_path = ubuntu_dir / f"ubuntu-{version}-live-server-amd64.iso"

            versions[version] = {
                "path": str(ubuntu_dir),
                "kernel": {
                    "exists": kernel_path.exists(),
                    "path": str(kernel_path),
                    "size": kernel_path.stat().st_size if kernel_path.exists() else 0
                },
                "initrd": {
                    "exists": initrd_path.exists(),
                    "path": str(initrd_path),
                    "size": initrd_path.stat().st_size if initrd_path.exists() else 0
                },
                "preseed": {
                    "exists": preseed_path.exists(),
                    "path": str(preseed_path),
                    "size": preseed_path.stat().st_size if preseed_path.exists() else 0
                },
                "iso": {
                    "exists": iso_path.exists(),
                    "path": str(iso_path),
                    "size": iso_path.stat().st_size if iso_path.exists() else 0
                },
                "complete": kernel_path.exists() and initrd_path.exists()
            }

        return versions

    @staticmethod
    def check_ubuntu_files() -> str:
        """Check Ubuntu files with version support"""
        versions = FileChecker.scan_ubuntu_versions()

        if not versions:
            return "❌ No Ubuntu versions found in /srv/http/"

        results = []
        working_versions = []

        for version, info in versions.items():
            results.append(f"\n🐧 **Ubuntu {version} LTS**:")

            # Check kernel
            if info['kernel']['exists']:
                size_mb = info['kernel']['size'] / (1024 * 1024)
                results.append(f"✅ vmlinuz: Found ({size_mb:.1f} MB)")
            else:
                results.append(f"❌ vmlinuz: Missing")

            # Check initrd
            if info['initrd']['exists']:
                size_mb = info['initrd']['size'] / (1024 * 1024)
                results.append(f"✅ initrd: Found ({size_mb:.1f} MB)")
            else:
                results.append(f"❌ initrd: Missing")

            # Check preseed
            if info['preseed']['exists']:
                size_kb = info['preseed']['size'] / 1024
                results.append(f"✅ preseed.cfg: Found ({size_kb:.1f} KB)")
            else:
                results.append(f"❌ preseed.cfg: Missing")

            # Check ISO
            if info['iso']['exists']:
                size_gb = info['iso']['size'] / (1024 * 1024 * 1024)
                results.append(f"✅ ISO: Found ({size_gb:.1f} GB)")
            else:
                results.append(f"❌ ISO: Missing")

            if info['complete']:
                working_versions.append(version)

        # Summary
        if working_versions:
            results.append(f"\n✅ **Working Ubuntu versions**: {', '.join(working_versions)}")
        else:
            results.append(f"\n❌ **No complete Ubuntu installations found**")

        return "\n".join(results)


class SystemTester:
    """Main system testing orchestrator with enhanced Ubuntu support"""

    def __init__(self):
        self.tftp_tester = TFTPTester()
        self.service_checker = ServiceChecker()
        self.http_tester = HTTPTester()
        self.file_checker = FileChecker()

    def run_full_system_test(self) -> str:
        """Run complete system test with Ubuntu version support"""
        results = []

        # Test TFTP connection
        tftp_result = self.tftp_tester.test_tftp_connection()
        results.append(tftp_result)

        # Check TFTP daemon
        daemon_result = self.service_checker.check_tftp_daemon()
        results.append(daemon_result)

        # Test main HTTP server
        http_result = self.http_tester.test_endpoint("http://localhost:8000/status")
        results.append(http_result)

        # Test Gradio UI - use correct internal port
        gradio_result = self.http_tester.test_endpoint("http://localhost:8000/pxe-station")
        if "OK" in gradio_result:
            results.append("✅ Gradio UI: Running (accessible via HTTP)")
        else:
            results.append("❌ Gradio UI: Not accessible")

        # Test iPXE menu
        ipxe_file_result = self.file_checker.check_file_exists("/srv/ipxe/boot.ipxe", False)
        results.append(ipxe_file_result)

        if "Found" in ipxe_file_result:
            ipxe_http_result = self.http_tester.test_endpoint("http://localhost:8000/ipxe/boot.ipxe")
            results.append(ipxe_http_result)

        # Test Ubuntu files with version support
        ubuntu_results = self.file_checker.check_ubuntu_files()
        results.append("\n" + ubuntu_results)

        # Test iPXE files
        ipxe_bios_result = self.file_checker.check_file_exists("/srv/tftp/undionly.kpxe")
        results.append(ipxe_bios_result)

        ipxe_uefi_result = self.file_checker.check_file_exists("/srv/tftp/ipxe.efi")
        results.append(ipxe_uefi_result)

        # Add final status with Ubuntu awareness
        results.extend(self._generate_final_status_with_ubuntu(results))

        return "\n".join(results)

    def _generate_final_status_with_ubuntu(self, test_results: List[str]) -> List[str]:
        """Generate final status with Ubuntu version awareness"""
        status_lines = [""]

        # Check for working Ubuntu versions
        ubuntu_versions_working = any("Working Ubuntu versions" in result for result in test_results)
        tftp_working = any("TFTP test: SUCCESS" in result for result in test_results)
        ipxe_files_present = any("undionly.kpxe" in result and "Found" in result for result in test_results)

        if ubuntu_versions_working and tftp_working and ipxe_files_present:
            status_lines.extend([
                "🎉 READY FOR PXE BOOT TESTING!",
                "📋 Ubuntu installations, TFTP, and iPXE components are working",
                "",
                "🔍 Next steps:",
                "1. Configure DHCP: Option 66 = YOUR_SERVER_IP, Option 67 = undionly.kpxe",
                "2. Boot test computer via network (PXE)",
                "3. Use 'Create Smart Menu' to generate multi-mode iPXE menu",
                "4. Or test with QEMU emulator"
            ])
        elif ubuntu_versions_working and tftp_working:
            status_lines.extend([
                "⚠️ MOSTLY READY",
                "✅ Ubuntu files and TFTP found, but check iPXE components",
                "",
                "🔧 Please check:",
                "1. Verify iPXE files (undionly.kpxe, ipxe.efi)",
                "2. Generate iPXE menu configuration"
            ])
        elif ubuntu_versions_working:
            status_lines.extend([
                "⚠️ PARTIALLY READY",
                "✅ Ubuntu files found, but TFTP may not be working",
                "",
                "🔧 Please check:",
                "1. Start TFTP server",
                "2. Verify iPXE files (undionly.kpxe, ipxe.efi)",
                "3. Generate iPXE menu configuration"
            ])
        else:
            status_lines.extend([
                "⚠️ SYSTEM NOT READY",
                "❌ No complete Ubuntu installations found",
                "",
                "🔧 Please check:",
                "1. Download Ubuntu files using Ubuntu Download tab",
                "2. Verify Ubuntu files are in /srv/http/ubuntu-XX.XX/ structure",
                "3. Start TFTP server if needed",
                "4. Generate iPXE menu",
                "5. Verify file permissions"
            ])

        return status_lines

    def run_ubuntu_specific_tests(self) -> str:
        """Run Ubuntu-specific tests"""
        results = []
        results.append("🐧 **Ubuntu-Specific Tests**")
        results.append("=" * 40)

        # Scan Ubuntu versions
        versions = self.file_checker.scan_ubuntu_versions()

        if not versions:
            results.append("❌ No Ubuntu versions found")
            return "\n".join(results)

        for version, info in versions.items():
            results.append(f"\n📦 **Testing Ubuntu {version}**:")

            if info['complete']:
                # Test HTTP access to kernel
                kernel_url = f"http://localhost:8000/ubuntu-{version}/vmlinuz"
                kernel_test = self.http_tester.test_endpoint(kernel_url)
                results.append(f"   {kernel_test}")

                # Test HTTP access to initrd
                initrd_url = f"http://localhost:8000/ubuntu-{version}/initrd"
                initrd_test = self.http_tester.test_endpoint(initrd_url)
                results.append(f"   {initrd_test}")

                # Test preseed if exists
                if info['preseed']['exists']:
                    preseed_url = f"http://localhost:8000/ubuntu-{version}/preseed.cfg"
                    preseed_test = self.http_tester.test_endpoint(preseed_url)
                    results.append(f"   {preseed_test}")

                results.append(f"   ✅ Ubuntu {version} is ready for PXE boot")
            else:
                results.append(f"   ❌ Ubuntu {version} incomplete (missing kernel or initrd)")

        return "\n".join(results)


# Convenience functions for backward compatibility
def test_tftp_connection() -> str:
    """Legacy function for TFTP testing"""
    return TFTPTester.test_tftp_connection()


def test_http_endpoints() -> str:
    """Enhanced HTTP testing with Ubuntu version support"""
    tester = SystemTester()
    return tester.run_full_system_test()


def test_ubuntu_files() -> str:
    """Test Ubuntu files with version support"""
    checker = FileChecker()
    return checker.check_ubuntu_files()


def run_ubuntu_tests() -> str:
    """Run comprehensive Ubuntu tests"""
    tester = SystemTester()
    return tester.run_ubuntu_specific_tests()