"""
Ubuntu downloader for PXE Boot Station - Multi-version Support
Downloads Ubuntu netboot files and manages Ubuntu-related assets with version separation
REFACTORED: Using common utilities to eliminate repetition
"""

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Import common utilities to eliminate repetition
from app.backend.utils import (
    calculate_total_size,
    download_with_progress,
    ensure_directory,
    format_file_size,
    safe_delete_directory,
    safe_operation,
    safe_write_file,
)


class UbuntuDownloader:
    """Ubuntu files downloader with multi-version support"""

    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = "/srv/http"  # Docker standard

        self.base_path = Path(base_path)

        # Configuration for Docker
        self.versions = {
            "24.04": {
                "name": "Ubuntu 24.04.2 LTS (Noble)",
                "method": "iso_extract",
                "iso_url": "https://releases.ubuntu.com/noble/ubuntu-24.04.2-live-server-amd64.iso",
                "size_mb": 2800,
            },
            "22.04": {
                "name": "Ubuntu 22.04.5 LTS (Jammy)",
                "method": "iso_extract",
                "iso_url": "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-live-server-amd64.iso",
                "size_mb": 2400,
            },
            "20.04": {
                "name": "Ubuntu 20.04.6 LTS (Focal)",
                "method": "netboot",
                "netboot_url": "http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/netboot.tar.gz",
                "size_mb": 35,
            },
        }

    def get_ubuntu_dir(self, version: str) -> Path:
        """Get version-specific Ubuntu directory"""
        return self.base_path / f"ubuntu-{version}"

    def get_installed_versions(self) -> List[str]:
        """Scan and return list of installed Ubuntu versions"""
        installed_versions = []

        try:
            if not self.base_path.exists():
                return installed_versions

            # Scan for ubuntu-* directories
            for item in self.base_path.iterdir():
                if item.is_dir() and item.name.startswith("ubuntu-"):
                    # Extract version from directory name (ubuntu-22.04 -> 22.04)
                    version_match = re.match(r"ubuntu-(.+)", item.name)
                    if version_match:
                        version = version_match.group(1)
                        # Check if this version has required files
                        ubuntu_dir = self.get_ubuntu_dir(version)
                        if (ubuntu_dir / "vmlinuz").exists() and (ubuntu_dir / "initrd").exists():
                            installed_versions.append(version)

            # Sort versions
            installed_versions.sort(reverse=True)  # Newest first

        except Exception:
            pass

        return installed_versions

    @safe_operation("Ubuntu files download")
    def download_all_files(
        self,
        version: str = "20.04",
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> str:
        """Download Ubuntu files for specific version"""
        if version not in self.versions:
            return f"❌ Unsupported Ubuntu version: {version}"

        version_info = self.versions[version]
        ubuntu_dir = self.get_ubuntu_dir(version)

        # Create version-specific directory
        ensure_directory(ubuntu_dir)

        status = f"🔄 Downloading {version_info['name']} to ubuntu-{version}/...\n"

        # Choose download method
        if version_info["method"] == "netboot":
            result = self._download_netboot(version, progress_callback)
        elif version_info["method"] == "iso_extract":
            result = self._download_and_extract_iso_docker(version, progress_callback)
        else:
            result = "❌ Unknown download method"

        status += result + "\n"

        # Create preseed
        preseed_result = self._create_preseed_config(version)
        status += preseed_result + "\n"

        # Final check
        check_result = self.check_files_status(version)
        status += "\n📋 Final Status:\n" + check_result

        return status

    @safe_operation("ISO download and extraction")
    def _download_and_extract_iso_docker(
        self, version: str, progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """Download and extract ISO - Docker optimized with system tools"""
        version_info = self.versions[version]
        iso_url = version_info["iso_url"]
        ubuntu_dir = self.get_ubuntu_dir(version)

        status = f"📥 Downloading Ubuntu ISO ({version_info['size_mb']} MB)...\n"

        # Download ISO using common utility
        iso_path = f"/tmp/ubuntu-{version}.iso"
        success, download_result = download_with_progress(
            url=iso_url,
            filepath=iso_path,
            filename=f"ubuntu-{version}.iso",
            progress_callback=progress_callback,
        )

        status += download_result + "\n"

        if not success:
            return status

        status += "📦 Extracting files from ISO using 7-Zip...\n"

        # Extract using 7-zip (fast and reliable)
        extract_result = self._extract_iso_with_7zip(iso_path, version)
        status += extract_result

        # Move ISO to final location
        try:
            target_iso_path = ubuntu_dir / f"ubuntu-{version}-live-server-amd64.iso"
            shutil.move(iso_path, target_iso_path)
            iso_size_human = format_file_size(target_iso_path.stat().st_size)
            status += f"💿 ISO saved to {target_iso_path}\n"
            status += f"📊 ISO size: {iso_size_human}\n"
        except Exception as e:
            status += f"⚠️ Failed to save ISO: {str(e)}\n"

        return status

    @safe_operation("Netboot download")
    def _download_netboot(
        self, version: str, progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """Download traditional netboot tarball (20.04, 24.04)"""
        version_info = self.versions[version]
        netboot_url = version_info["netboot_url"]

        status = f"📥 Downloading netboot tarball ({version_info['size_mb']} MB)...\n"

        # Download with progress tracking using common utility
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp_file:
            tmp_path = tmp_file.name

        success, download_result = download_with_progress(
            url=netboot_url,
            filepath=tmp_path,
            filename=f"netboot-{version}.tar.gz",
            progress_callback=progress_callback,
        )

        status += download_result + "\n"

        if not success:
            return status

        status += "📦 Extracting netboot files...\n"

        # Extract and process files
        extract_result = self._extract_netboot(tmp_path, version)
        status += extract_result

        # Clean up
        Path(tmp_path).unlink()

        return status

    @safe_operation("Netboot extraction")
    def _extract_netboot(self, tar_path: str, version: str) -> str:
        """Extract netboot files from tarball with IMPROVED logic"""
        status = ""
        kernel_found = False
        initrd_found = False
        ubuntu_dir = self.get_ubuntu_dir(version)

        with tarfile.open(tar_path, "r:gz") as tar:
            # List all files for debugging
            all_files = [member.name for member in tar.getmembers() if member.isfile()]
            status += f"📋 Found {len(all_files)} files in archive\n"

            # IMPROVED LOGIC: find best candidates first
            kernel_candidates = []
            initrd_candidates = []

            for member in tar.getmembers():
                if not member.isfile():
                    continue

                member_basename = member.name.split("/")[-1].lower()  # Only filename

                # Search for initrd files
                if any(pattern in member_basename for pattern in ["initrd", "initramfs"]):
                    initrd_candidates.append(
                        (member, len(member_basename))
                    )  # Priority by name length

                # Search for kernel files with EXACT criteria
                elif (
                    # Must contain linux/vmlinuz/kernel
                    any(pattern in member_basename for pattern in ["linux", "vmlinuz", "kernel"])
                    and
                    # Must NOT contain exclusions
                    not any(
                        pattern in member_basename
                        for pattern in [
                            "initrd",
                            "initramfs",
                            ".txt",
                            ".cfg",
                            ".md5",
                            "ldlinux",
                            "pxelinux",
                            ".c32",
                            ".0",
                            "syslinux",
                            "menu",
                            "chain",
                            "mboot",
                        ]
                    )
                    and
                    # Prefer files without extension or with .bin extension
                    (("." not in member_basename) or member_basename.endswith(".bin"))
                ):
                    # Priority: exact name "linux" > "vmlinuz" > others
                    priority = 0
                    if member_basename == "linux":
                        priority = 100
                    elif member_basename.startswith("vmlinuz"):
                        priority = 90
                    elif "kernel" in member_basename:
                        priority = 80
                    else:
                        priority = 70

                    kernel_candidates.append((member, priority))

            # Sort candidates by priority
            kernel_candidates.sort(key=lambda x: x[1], reverse=True)
            initrd_candidates.sort(key=lambda x: x[1])  # Shorter names preferred

            # Extract BEST kernel
            if kernel_candidates:
                best_kernel = kernel_candidates[0][0]
                with tar.extractfile(best_kernel) as kernel_file:
                    with open(ubuntu_dir / "vmlinuz", "wb") as f:
                        shutil.copyfileobj(kernel_file, f)
                status += f"✅ Extracted kernel: {best_kernel.name}\n"
                kernel_found = True

                # Show rejected candidates for debugging
                if len(kernel_candidates) > 1:
                    rejected = [k[0].name for k in kernel_candidates[1:]]
                    status += f"🔍 Rejected kernel candidates: {rejected}\n"

            # Extract BEST initrd
            if initrd_candidates:
                best_initrd = initrd_candidates[0][0]
                with tar.extractfile(best_initrd) as initrd_file:
                    with open(ubuntu_dir / "initrd", "wb") as f:
                        shutil.copyfileobj(initrd_file, f)
                status += f"✅ Extracted initrd: {best_initrd.name}\n"
                initrd_found = True

        # Report results
        if kernel_found and initrd_found:
            status += "🎉 All netboot files extracted successfully!\n"
        else:
            missing = []
            if not kernel_found:
                missing.append("kernel")
                status += f"❌ No valid kernel found. Files in archive: {all_files}\n"
            if not initrd_found:
                missing.append("initrd")
                status += f"❌ No valid initrd found. Files in archive: {all_files}\n"
            status += f"⚠️ Extraction incomplete. Missing: {', '.join(missing)}\n"

        return status

    @safe_operation("ISO extraction with 7-Zip")
    def _extract_iso_with_7zip(self, iso_path: str, version: str) -> str:
        """Extract ISO using 7-zip - fast and reliable"""
        status = ""
        extract_dir = f"/tmp/extract-{version}"
        ubuntu_dir = self.get_ubuntu_dir(version)

        # Create extraction directory
        ensure_directory(extract_dir)

        # Extract ISO with 7-zip
        cmd = ["7z", "x", iso_path, f"-o{extract_dir}", "-y"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return f"❌ 7-Zip extraction failed: {result.stderr}"

        status += "✅ ISO extracted with 7-Zip\n"

        # Find kernel and initrd
        search_paths = [
            ("casper/vmlinuz", "casper/initrd"),
            ("casper/vmlinuz.efi", "casper/initrd.lz"),
            ("install/vmlinuz", "install/initrd.gz"),
            ("live/vmlinuz", "live/initrd"),
        ]

        kernel_found = False
        initrd_found = False

        for kernel_rel, initrd_rel in search_paths:
            kernel_path = os.path.join(extract_dir, kernel_rel)
            initrd_path = os.path.join(extract_dir, initrd_rel)

            if os.path.exists(kernel_path) and os.path.exists(initrd_path):
                # Copy files to version-specific directory
                shutil.copy2(kernel_path, ubuntu_dir / "vmlinuz")
                shutil.copy2(initrd_path, ubuntu_dir / "initrd")

                status += f"✅ Extracted kernel: {kernel_rel}\n"
                status += f"✅ Extracted initrd: {initrd_rel}\n"

                kernel_found = True
                initrd_found = True
                break

        # Cleanup extraction directory
        try:
            shutil.rmtree(extract_dir)
            status += "🧹 Extraction directory cleaned up\n"
        except Exception as e:
            # Log but don't fail - cleanup is best-effort
            status += f"⚠️ Failed to cleanup temp directory: {str(e)}\n"

        if kernel_found and initrd_found:
            status += "🎉 ISO extraction completed successfully!\n"
        else:
            # List available files for debugging
            status += "❌ Could not find kernel/initrd files\n"
            try:
                available_files = []
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if any(
                            pattern in file.lower()
                            for pattern in ["vmlinuz", "linux", "initrd", "kernel"]
                        ):
                            rel_path = os.path.relpath(os.path.join(root, file), extract_dir)
                            available_files.append(rel_path)
                status += f"🔍 Available files: {available_files[:10]}\n"
            except Exception:
                pass

        return status

    @safe_operation("Preseed configuration creation")
    def _create_preseed_config(self, version: str) -> str:
        """Create preseed configuration file for specific version"""
        version_info = self.versions[version]
        ubuntu_dir = self.get_ubuntu_dir(version)

        preseed_content = f"""# {version_info['name']} Preseed Configuration
# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# Locale and keyboard
d-i debian-installer/locale string en_US
d-i console-setup/ask_detect boolean false
d-i keyboard-configuration/xkb-keymap select us

# Network configuration
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string ubuntu
d-i netcfg/get_domain string localdomain
d-i netcfg/wireless_wep string

# Mirror settings
d-i mirror/country string manual
d-i mirror/http/hostname string archive.ubuntu.com
d-i mirror/http/directory string /ubuntu
d-i mirror/http/proxy string

# Clock and time zone
d-i clock-setup/utc boolean true
d-i time/zone string UTC
d-i clock-setup/ntp boolean true

# Partitioning
d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

# User account
d-i passwd/user-fullname string Ubuntu User
d-i passwd/username string ubuntu
d-i passwd/user-password password ubuntu
d-i passwd/user-password-again password ubuntu
d-i user-setup/allow-password-weak boolean true

# Package selection
tasksel tasksel/first multiselect ubuntu-server
d-i pkgsel/include string openssh-server curl wget nano
d-i pkgsel/upgrade select full-upgrade
d-i pkgsel/update-policy select unattended-upgrades

# Boot loader
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true

# Finish installation
d-i finish-install/reboot_in_progress note
"""

        success, message = safe_write_file(ubuntu_dir / "preseed.cfg", preseed_content)
        if success:
            return f"✅ Preseed configuration created for {version}"
        return message

    def check_files_status(self, version: str = None) -> str:
        """Check status of Ubuntu files for specific version or all versions"""
        if version:
            # Check specific version
            return self._check_single_version_status(version)
        else:
            # Check all installed versions
            return self._check_all_versions_status()

    def _check_single_version_status(self, version: str) -> str:
        """Check files for a single version"""
        ubuntu_dir = self.get_ubuntu_dir(version)
        files_info = []

        files_info.append(f"📁 **Ubuntu {version}** - {ubuntu_dir}")

        # Check kernel
        kernel_path = ubuntu_dir / "vmlinuz"
        if kernel_path.exists():
            size_human = format_file_size(kernel_path.stat().st_size)
            mod_time = datetime.fromtimestamp(kernel_path.stat().st_mtime)
            files_info.append(f"✅ vmlinuz ({size_human}) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
        else:
            files_info.append("❌ vmlinuz (missing)")

        # Check initrd
        initrd_path = ubuntu_dir / "initrd"
        if initrd_path.exists():
            size_human = format_file_size(initrd_path.stat().st_size)
            mod_time = datetime.fromtimestamp(initrd_path.stat().st_mtime)
            files_info.append(f"✅ initrd ({size_human}) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
        else:
            files_info.append("❌ initrd (missing)")

        # Check preseed
        preseed_path = ubuntu_dir / "preseed.cfg"
        if preseed_path.exists():
            size_human = format_file_size(preseed_path.stat().st_size)
            mod_time = datetime.fromtimestamp(preseed_path.stat().st_mtime)
            files_info.append(
                f"✅ preseed.cfg ({size_human}) - {mod_time.strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            files_info.append("❌ preseed.cfg (missing)")

        # Add directory info
        if ubuntu_dir.exists():
            total_files = len(list(ubuntu_dir.iterdir()))
            files_info.append(f"📊 Total files: {total_files}")
        else:
            files_info.append("❌ Directory does not exist")

        return "\n".join(files_info)

    def _check_all_versions_status(self) -> str:
        """Check files for all installed versions"""
        installed_versions = self.get_installed_versions()

        if not installed_versions:
            return (
                f"📁 No Ubuntu versions installed in {self.base_path}\n\n"
                f"🔍 Available versions to download: {', '.join(self.versions.keys())}"
            )

        results = []
        results.append(f"📁 Ubuntu installations in {self.base_path}")
        results.append("=" * 50)

        total_size = 0
        for version in installed_versions:
            version_status = self._check_single_version_status(version)
            results.append(version_status)
            results.append("")

            # Calculate total size using common utility
            ubuntu_dir = self.get_ubuntu_dir(version)
            if ubuntu_dir.exists():
                total_size += calculate_total_size(ubuntu_dir)

        # Add summary
        results.append("📊 **SUMMARY**")
        results.append(f"📁 Installed versions: {len(installed_versions)}")
        results.append(f"💾 Total disk usage: {format_file_size(total_size)}")
        results.append(f"🔢 Available versions: {', '.join(self.versions.keys())}")

        return "\n".join(results)

    def delete_version(self, version: str) -> str:
        """Delete specific Ubuntu version"""
        ubuntu_dir = self.get_ubuntu_dir(version)

        if not ubuntu_dir.exists():
            return f"ℹ️ Ubuntu {version} is not installed: {ubuntu_dir}"

        # Use common utility for safe deletion
        success, message, freed_bytes = safe_delete_directory(ubuntu_dir)

        if success:
            return f"✅ Ubuntu {version} deleted - {message}\n📁 Path: {ubuntu_dir}"

        return f"❌ Error deleting Ubuntu {version}: {message}"

    def delete_all_versions(self) -> str:
        """Delete all Ubuntu versions"""
        installed_versions = self.get_installed_versions()

        if not installed_versions:
            return "ℹ️ No Ubuntu versions to delete"

        deleted_versions = []
        total_freed = 0

        for version in installed_versions:
            ubuntu_dir = self.get_ubuntu_dir(version)
            if ubuntu_dir.exists():
                success, message, freed_bytes = safe_delete_directory(ubuntu_dir)
                if success:
                    deleted_versions.append(version)
                    total_freed += freed_bytes

        total_freed_human = format_file_size(total_freed)
        return (
            f"✅ Deleted {len(deleted_versions)} Ubuntu versions: {', '.join(deleted_versions)}\n"
            f"💾 Total freed: {total_freed_human}"
        )

    def get_supported_versions(self) -> Dict[str, Any]:
        """Get list of supported Ubuntu versions"""
        return self.versions

    def get_version_info(self, version: str) -> Dict[str, Any]:
        """Get information about specific version"""
        if version in self.versions:
            info = self.versions[version].copy()
            ubuntu_dir = self.get_ubuntu_dir(version)
            info["installed"] = ubuntu_dir.exists() and (ubuntu_dir / "vmlinuz").exists()
            info["install_path"] = str(ubuntu_dir)
            return info
        return {}


# Legacy functions for backward compatibility
def download_ubuntu_netboot(version: str = "24.04") -> str:
    """Legacy function - download Ubuntu netboot files"""
    downloader = UbuntuDownloader()
    return downloader.download_all_files(version)


def check_ubuntu_files() -> str:
    """Legacy function - check Ubuntu files status"""
    downloader = UbuntuDownloader()
    return downloader.check_files_status()
