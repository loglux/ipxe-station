import requests
import tarfile
import tempfile
from pathlib import Path
import shutil
import os
import subprocess
from typing import Callable, Optional, Dict, Any
from datetime import datetime


class UbuntuDownloader:
    """Ubuntu files downloader with version-specific directories"""

    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = "/srv/http"

        self.base_path = Path(base_path)
        # We don't create a shared ubuntu folder in advance.

        self.versions = {
            "24.04": {
                "name": "Ubuntu 24.04.2 LTS (Noble)",
                "method": "iso_extract",
                "iso_url": "https://releases.ubuntu.com/noble/ubuntu-24.04.2-live-server-amd64.iso",
                "size_mb": 2800,
                "dir_name": "ubuntu-24.04"  # Separate folder
            },
            "22.04": {
                "name": "Ubuntu 22.04.5 LTS (Jammy)",
                "method": "iso_extract",
                "iso_url": "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-live-server-amd64.iso",
                "size_mb": 2400,
                "dir_name": "ubuntu-22.04"  # Separate folder
            },
            "20.04": {
                "name": "Ubuntu 20.04.6 LTS (Focal)",
                "method": "netboot",
                "netboot_url": "http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/netboot.tar.gz",
                "size_mb": 35,
                "dir_name": "ubuntu-20.04"  # Separate folder
            }
        }

    def get_version_directory(self, version: str) -> Path:
        """Получить путь к папке конкретной версии"""
        if version not in self.versions:
            raise ValueError(f"Unsupported version: {version}")

        dir_name = self.versions[version]["dir_name"]
        return self.base_path / dir_name

    def download_all_files(self, version: str = "20.04",
                           progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download Ubuntu files for specific version"""
        try:
            if version not in self.versions:
                return f"❌ Unsupported Ubuntu version: {version}"

            version_info = self.versions[version]

            # Создаем папку для конкретной версии
            version_dir = self.get_version_directory(version)
            version_dir.mkdir(parents=True, exist_ok=True)

            status = f"🔄 Downloading {version_info['name']}...\n"
            status += f"📁 Target directory: {version_dir}\n"

            # Выбираем метод загрузки
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

        except Exception as e:
            return f"❌ Error downloading Ubuntu files: {str(e)}"

    def _download_and_extract_iso_docker(self, version: str,
                                         progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download and extract ISO to version-specific directory"""
        try:
            version_info = self.versions[version]
            version_dir = self.get_version_directory(version)
            iso_url = version_info["iso_url"]

            status = f"📥 Downloading Ubuntu ISO ({version_info['size_mb']} MB)...\n"

            # Download ISO
            iso_path = f"/tmp/ubuntu-{version}.iso"
            download_result = self._download_file_fast(iso_url, iso_path, f"ubuntu-{version}.iso", progress_callback)
            status += download_result + "\n"

            if "✅" not in download_result:
                return status

            status += "📦 Extracting files from ISO using 7-Zip...\n"

            # Extract using 7-zip to version-specific directory
            extract_result = self._extract_iso_with_7zip(iso_path, version, version_dir)
            status += extract_result

            # Cleanup
            try:
                os.unlink(iso_path)
                status += "🧹 Temporary ISO cleaned up\n"
            except:
                pass

            return status

        except Exception as e:
            return f"❌ Error in Docker ISO processing: {str(e)}"

    def _extract_iso_with_7zip(self, iso_path: str, version: str, target_dir: Path) -> str:
        """Extract ISO using 7-zip to specific directory"""
        try:
            status = ""
            extract_dir = f"/tmp/extract-{version}"

            # Create extraction directory
            os.makedirs(extract_dir, exist_ok=True)

            # Extract ISO with 7-zip
            cmd = ['7z', 'x', iso_path, f'-o{extract_dir}', '-y']
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
                    shutil.copy2(kernel_path, target_dir / "vmlinuz")
                    shutil.copy2(initrd_path, target_dir / "initrd")

                    status += f"✅ Extracted kernel: {kernel_rel}\n"
                    status += f"✅ Extracted initrd: {initrd_rel}\n"

                    kernel_found = True
                    initrd_found = True
                    break

            # Cleanup extraction directory
            try:
                shutil.rmtree(extract_dir)
                status += "🧹 Extraction directory cleaned up\n"
            except:
                pass

            if kernel_found and initrd_found:
                status += "🎉 ISO extraction completed successfully!\n"
            else:
                status += "❌ Could not find kernel/initrd files\n"

            return status

        except subprocess.TimeoutExpired:
            return "❌ 7-Zip extraction timed out (>5 minutes)"
        except Exception as e:
            return f"❌ Error extracting ISO: {str(e)}"

    def _download_netboot(self, version: str,
                          progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download traditional netboot tarball to version-specific directory"""
        try:
            version_info = self.versions[version]
            version_dir = self.get_version_directory(version)
            netboot_url = version_info["netboot_url"]

            status = f"📥 Downloading netboot tarball ({version_info['size_mb']} MB)...\n"

            # Download with progress tracking
            response = requests.get(netboot_url, timeout=300, stream=True)
            if response.status_code != 200:
                return f"❌ Failed to download netboot: HTTP {response.status_code}"

            # Get total size
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            # Save to temporary file with progress
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size, f"netboot-{version}.tar.gz")

                tmp_path = tmp_file.name

            status += "✅ Netboot tarball downloaded\n"
            status += "📦 Extracting netboot files...\n"

            # Extract and process files to version-specific directory
            extract_result = self._extract_netboot(tmp_path, version, version_dir)
            status += extract_result

            # Clean up
            Path(tmp_path).unlink()

            return status

        except Exception as e:
            return f"❌ Error downloading netboot: {str(e)}"

    def _extract_netboot(self, tar_path: str, version: str, target_dir: Path) -> str:
        """Extract netboot files from tarball to specific directory"""
        try:
            status = ""
            kernel_found = False
            initrd_found = False

            with tarfile.open(tar_path, 'r:gz') as tar:
                # List all files
                all_files = [member.name for member in tar.getmembers() if member.isfile()]
                status += f"📋 Found {len(all_files)} files in archive\n"

                # Find candidates
                kernel_candidates = []
                initrd_candidates = []

                for member in tar.getmembers():
                    if not member.isfile():
                        continue

                    member_name = member.name.lower()
                    member_basename = member.name.split('/')[-1].lower()

                    # Search for initrd files
                    if any(pattern in member_basename for pattern in ['initrd', 'initramfs']):
                        initrd_candidates.append((member, len(member_basename)))

                    # Search for kernel files
                    elif (
                            any(pattern in member_basename for pattern in ['linux', 'vmlinuz', 'kernel']) and
                            not any(pattern in member_basename for pattern in [
                                'initrd', 'initramfs', '.txt', '.cfg', '.md5', 'ldlinux', 'pxelinux',
                                '.c32', '.0', 'syslinux', 'menu', 'chain', 'mboot'
                            ]) and
                            (('.' not in member_basename) or member_basename.endswith('.bin'))
                    ):
                        priority = 0
                        if member_basename == 'linux':
                            priority = 100
                        elif member_basename.startswith('vmlinuz'):
                            priority = 90
                        elif 'kernel' in member_basename:
                            priority = 80
                        else:
                            priority = 70

                        kernel_candidates.append((member, priority))

                # Sort by priority
                kernel_candidates.sort(key=lambda x: x[1], reverse=True)
                initrd_candidates.sort(key=lambda x: x[1])

                # Extract best kernel to version-specific directory
                if kernel_candidates:
                    best_kernel = kernel_candidates[0][0]
                    with tar.extractfile(best_kernel) as kernel_file:
                        with open(target_dir / "vmlinuz", "wb") as f:
                            shutil.copyfileobj(kernel_file, f)
                    status += f"✅ Extracted kernel: {best_kernel.name}\n"
                    kernel_found = True

                # Extract best initrd to version-specific directory
                if initrd_candidates:
                    best_initrd = initrd_candidates[0][0]
                    with tar.extractfile(best_initrd) as initrd_file:
                        with open(target_dir / "initrd", "wb") as f:
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
                if not initrd_found:
                    missing.append("initrd")
                status += f"⚠️ Extraction incomplete. Missing: {', '.join(missing)}\n"

            return status

        except Exception as e:
            return f"❌ Error extracting netboot: {str(e)}"

    def _create_preseed_config(self, version: str) -> str:
        """Create preseed configuration file in version-specific directory"""
        try:
            version_info = self.versions[version]
            version_dir = self.get_version_directory(version)

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

            with open(version_dir / "preseed.cfg", "w") as f:
                f.write(preseed_content)

            return "✅ Preseed configuration created"

        except Exception as e:
            return f"❌ Error creating preseed: {str(e)}"

    def check_files_status(self, version: str = None) -> str:
        """Check status of Ubuntu files for specific version"""
        try:
            if version is None:
                # Check all versions
                return self._check_all_versions_status()

            version_dir = self.get_version_directory(version)
            version_info = self.versions[version]

            files_info = []
            files_info.append(f"📁 {version_info['name']} - {version_dir}")

            # Check kernel
            kernel_path = version_dir / "vmlinuz"
            if kernel_path.exists():
                size_mb = kernel_path.stat().st_size / (1024 * 1024)
                mod_time = datetime.fromtimestamp(kernel_path.stat().st_mtime)
                files_info.append(f"✅ vmlinuz ({size_mb:.1f} MB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                files_info.append("❌ vmlinuz (missing)")

            # Check initrd
            initrd_path = version_dir / "initrd"
            if initrd_path.exists():
                size_mb = initrd_path.stat().st_size / (1024 * 1024)
                mod_time = datetime.fromtimestamp(initrd_path.stat().st_mtime)
                files_info.append(f"✅ initrd ({size_mb:.1f} MB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                files_info.append("❌ initrd (missing)")

            # Check preseed
            preseed_path = version_dir / "preseed.cfg"
            if preseed_path.exists():
                size_kb = preseed_path.stat().st_size / 1024
                mod_time = datetime.fromtimestamp(preseed_path.stat().st_mtime)
                files_info.append(f"✅ preseed.cfg ({size_kb:.1f} KB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                files_info.append("❌ preseed.cfg (missing)")

            # Add directory info
            if version_dir.exists():
                total_files = len(list(version_dir.iterdir()))
                files_info.append(f"📊 Total files: {total_files}")
            else:
                files_info.append(f"❌ Directory does not exist")

            return "\n".join(files_info)

        except Exception as e:
            return f"❌ Error checking files: {str(e)}"

    def _check_all_versions_status(self) -> str:
        """Check status of all Ubuntu versions"""
        try:
            all_status = []

            for version in self.versions.keys():
                version_status = self.check_files_status(version)
                all_status.append(version_status)
                all_status.append("")  # Empty line between versions

            return "\n".join(all_status)

        except Exception as e:
            return f"❌ Error checking all versions: {str(e)}"

    def get_supported_versions(self) -> Dict[str, Any]:
        """Get list of supported Ubuntu versions with their directories"""
        versions_with_dirs = {}
        for version, info in self.versions.items():
            versions_with_dirs[version] = {
                **info,
                "directory": str(self.get_version_directory(version))
            }
        return versions_with_dirs

    def delete_files(self, version: str = None) -> str:
        """Delete Ubuntu files for specific version or all versions"""
        try:
            if version is None:
                # Delete all versions
                deleted = []
                for ver in self.versions.keys():
                    version_dir = self.get_version_directory(ver)
                    if version_dir.exists():
                        shutil.rmtree(version_dir)
                        deleted.append(ver)

                if deleted:
                    return f"✅ Deleted Ubuntu files for versions: {', '.join(deleted)}"
                else:
                    return "ℹ️ No Ubuntu directories found to delete"
            else:
                # Delete specific version
                version_dir = self.get_version_directory(version)
                if version_dir.exists():
                    shutil.rmtree(version_dir)
                    return f"✅ Ubuntu {version} files deleted from {version_dir}"
                else:
                    return f"ℹ️ Ubuntu {version} directory does not exist: {version_dir}"

        except Exception as e:
            return f"❌ Error deleting files: {str(e)}"


# Legacy functions for backward compatibility
def download_ubuntu_netboot(version: str = "20.04") -> str:
    """Legacy function - download Ubuntu netboot files"""
    downloader = UbuntuDownloader()
    return downloader.download_all_files(version)


def check_ubuntu_files() -> str:
    """Legacy function - check Ubuntu files status for all versions"""
    downloader = UbuntuDownloader()
    return downloader.check_files_status()  # None = all versions