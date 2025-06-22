"""
Ubuntu downloader for PXE Boot Station
Downloads Ubuntu netboot files and manages Ubuntu-related assets
"""

import requests
import tarfile
import tempfile
from pathlib import Path
import shutil
import os
from typing import Callable, Optional, Dict, Any
from datetime import datetime


class UbuntuDownloader:
    """Ubuntu files downloader and manager"""

    def __init__(self, base_path: str = None):
        # Cross-platform base path
        if base_path is None:
            if os.name == 'nt':  # Windows
                base_path = "C:/srv/http"
            else:  # Unix-like
                base_path = "/srv/http"

        self.base_path = Path(base_path)
        self.ubuntu_dir = self.base_path / "ubuntu"

        # Ubuntu versions configuration with FIXED URLs
        self.versions = {
            "24.04": {
                "name": "Ubuntu 24.04.2 LTS (Noble)",
                "method": "netboot",  # Есть netboot
                "netboot_url": "https://cdimage.ubuntu.com/netboot/noble/ubuntu-installer-amd64.tar.gz",
                "size_mb": 45
            },
            "22.04": {
                "name": "Ubuntu 22.04.5 LTS (Jammy)",
                "method": "live",  # Нет netboot, используем live installer
                "live_url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso",
                "kernel_url": "https://cdimage.ubuntu.com/netboot/jammy/ubuntu-installer/amd64/linux",
                "initrd_url": "https://cdimage.ubuntu.com/netboot/jammy/ubuntu-installer/amd64/initrd.gz",
                "size_mb": 25  # Kernel + initrd
            },
            "20.04": {
                "name": "Ubuntu 20.04.6 LTS (Focal)",
                "method": "netboot",  # Есть legacy netboot
                "netboot_url": "http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/netboot.tar.gz",
                "size_mb": 35
            }
        }

    def download_all_files(self, version: str = "24.04",
                           progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download all Ubuntu files for specified version"""
        try:
            if version not in self.versions:
                return f"❌ Unsupported Ubuntu version: {version}"

            version_info = self.versions[version]

            # Create directory
            self.ubuntu_dir.mkdir(parents=True, exist_ok=True)

            status = f"🔄 Downloading {version_info['name']}...\n"

            # Выбираем метод загрузки в зависимости от версии
            if version_info["method"] == "netboot":
                result = self._download_netboot(version, progress_callback)
            elif version_info["method"] == "live":
                result = self._download_live_installer(version, progress_callback)
            else:
                result = "❌ Unknown download method"

            status += result + "\n"

            # Create preseed file
            preseed_result = self._create_preseed_config(version)
            status += preseed_result + "\n"

            # Final check
            check_result = self.check_files_status(version)
            status += "\n📋 Final Status:\n" + check_result

            return status

        except Exception as e:
            return f"❌ Error downloading Ubuntu files: {str(e)}"

    def _download_live_installer(self, version: str,
                                 progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download kernel and initrd for versions without netboot (22.04+)"""
        try:
            version_info = self.versions[version]

            status = f"📥 Downloading live installer components ({version_info['size_mb']} MB)...\n"

            # Download kernel
            kernel_result = self._download_file(
                version_info["kernel_url"],
                self.ubuntu_dir / "vmlinuz",
                "kernel",
                progress_callback
            )
            status += kernel_result + "\n"

            # Download initrd
            initrd_result = self._download_file(
                version_info["initrd_url"],
                self.ubuntu_dir / "initrd",
                "initrd",
                progress_callback
            )
            status += initrd_result + "\n"

            status += "✅ Live installer components downloaded\n"

            return status

        except Exception as e:
            return f"❌ Error downloading live installer: {str(e)}"

    def _download_file(self, url: str, filepath: Path, filename: str,
                       progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download a single file with progress tracking"""
        try:
            response = requests.get(url, timeout=120, stream=True)
            if response.status_code != 200:
                return f"❌ Failed to download {filename}: HTTP {response.status_code}"

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size, filename)

            size_mb = filepath.stat().st_size / (1024 * 1024)
            return f"✅ Downloaded {filename}: {size_mb:.1f} MB"

        except Exception as e:
            return f"❌ Error downloading {filename}: {str(e)}"

    def _download_netboot(self, version: str,
                          progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download traditional netboot tarball (20.04, 24.04)"""
        try:
            version_info = self.versions[version]
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

            # Extract and process files
            extract_result = self._extract_netboot(tmp_path, version)
            status += extract_result

            # Clean up
            Path(tmp_path).unlink()

            return status

        except Exception as e:
            return f"❌ Error downloading netboot: {str(e)}"

    def _extract_netboot(self, tar_path: str, version: str) -> str:
        """Extract netboot files from tarball with IMPROVED logic"""
        try:
            status = ""
            kernel_found = False
            initrd_found = False

            with tarfile.open(tar_path, 'r:gz') as tar:
                # List all files for debugging
                all_files = [member.name for member in tar.getmembers() if member.isfile()]
                status += f"📋 Found {len(all_files)} files in archive\n"

                # УЛУЧШЕННАЯ ЛОГИКА: сначала найдем лучшие кандидаты
                kernel_candidates = []
                initrd_candidates = []

                for member in tar.getmembers():
                    if not member.isfile():
                        continue

                    member_name = member.name.lower()
                    member_basename = member.name.split('/')[-1].lower()  # Только имя файла

                    # Ищем initrd файлы
                    if any(pattern in member_basename for pattern in ['initrd', 'initramfs']):
                        initrd_candidates.append((member, len(member_basename)))  # Приоритет по длине имени

                    # Ищем kernel файлы с ТОЧНЫМИ критериями
                    elif (
                            # Должен содержать linux/vmlinuz/kernel
                            any(pattern in member_basename for pattern in ['linux', 'vmlinuz', 'kernel']) and
                            # НЕ должен содержать исключения
                            not any(pattern in member_basename for pattern in [
                                'initrd', 'initramfs', '.txt', '.cfg', '.md5', 'ldlinux', 'pxelinux',
                                '.c32', '.0', 'syslinux', 'menu', 'chain', 'mboot'
                            ]) and
                            # Предпочитаем файлы без расширения или с расширением .bin
                            (('.' not in member_basename) or member_basename.endswith('.bin'))
                    ):
                        # Приоритет: точное имя "linux" > "vmlinuz" > остальные
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

                # Сортируем кандидатов по приоритету
                kernel_candidates.sort(key=lambda x: x[1], reverse=True)
                initrd_candidates.sort(key=lambda x: x[1])  # Более короткие имена предпочтительнее

                # Извлекаем ЛУЧШИЙ kernel
                if kernel_candidates:
                    best_kernel = kernel_candidates[0][0]
                    with tar.extractfile(best_kernel) as kernel_file:
                        with open(self.ubuntu_dir / "vmlinuz", "wb") as f:
                            shutil.copyfileobj(kernel_file, f)
                    status += f"✅ Extracted kernel: {best_kernel.name}\n"
                    kernel_found = True

                    # Показываем отклоненных кандидатов для отладки
                    if len(kernel_candidates) > 1:
                        rejected = [k[0].name for k in kernel_candidates[1:]]
                        status += f"🔍 Rejected kernel candidates: {rejected}\n"

                # Извлекаем ЛУЧШИЙ initrd
                if initrd_candidates:
                    best_initrd = initrd_candidates[0][0]
                    with tar.extractfile(best_initrd) as initrd_file:
                        with open(self.ubuntu_dir / "initrd", "wb") as f:
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

        except Exception as e:
            return f"❌ Error extracting netboot: {str(e)}"

    def _create_preseed_config(self, version: str) -> str:
        """Create preseed configuration file"""
        try:
            version_info = self.versions[version]

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

            with open(self.ubuntu_dir / "preseed.cfg", "w") as f:
                f.write(preseed_content)

            return "✅ Preseed configuration created"

        except Exception as e:
            return f"❌ Error creating preseed: {str(e)}"

    def check_files_status(self, version: str = None) -> str:
        """Check status of Ubuntu files"""
        try:
            files_info = []

            # Check kernel
            kernel_path = self.ubuntu_dir / "vmlinuz"
            if kernel_path.exists():
                size_mb = kernel_path.stat().st_size / (1024 * 1024)
                mod_time = datetime.fromtimestamp(kernel_path.stat().st_mtime)
                files_info.append(f"✅ vmlinuz ({size_mb:.1f} MB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                files_info.append("❌ vmlinuz (missing)")

            # Check initrd
            initrd_path = self.ubuntu_dir / "initrd"
            if initrd_path.exists():
                size_mb = initrd_path.stat().st_size / (1024 * 1024)
                mod_time = datetime.fromtimestamp(initrd_path.stat().st_mtime)
                files_info.append(f"✅ initrd ({size_mb:.1f} MB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                files_info.append("❌ initrd (missing)")

            # Check preseed
            preseed_path = self.ubuntu_dir / "preseed.cfg"
            if preseed_path.exists():
                size_kb = preseed_path.stat().st_size / 1024
                mod_time = datetime.fromtimestamp(preseed_path.stat().st_mtime)
                files_info.append(f"✅ preseed.cfg ({size_kb:.1f} KB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                files_info.append("❌ preseed.cfg (missing)")

            # Add directory info
            if self.ubuntu_dir.exists():
                total_files = len(list(self.ubuntu_dir.iterdir()))
                files_info.append(f"\n📁 Ubuntu directory: {self.ubuntu_dir}")
                files_info.append(f"📊 Total files: {total_files}")
            else:
                files_info.append(f"\n❌ Ubuntu directory does not exist: {self.ubuntu_dir}")

            return "\n".join(files_info)

        except Exception as e:
            return f"❌ Error checking files: {str(e)}"

    def get_supported_versions(self) -> Dict[str, Any]:
        """Get list of supported Ubuntu versions"""
        return self.versions

    def delete_files(self, version: str = None) -> str:
        """Delete Ubuntu files"""
        try:
            if self.ubuntu_dir.exists():
                shutil.rmtree(self.ubuntu_dir)
                return f"✅ Ubuntu files deleted from {self.ubuntu_dir}"
            else:
                return f"ℹ️ Ubuntu directory does not exist: {self.ubuntu_dir}"
        except Exception as e:
            return f"❌ Error deleting files: {str(e)}"


# Legacy functions for backward compatibility
def download_ubuntu_netboot(version: str = "24.04") -> str:
    """Legacy function - download Ubuntu netboot files"""
    downloader = UbuntuDownloader()
    return downloader.download_all_files(version)


def check_ubuntu_files() -> str:
    """Legacy function - check Ubuntu files status"""
    downloader = UbuntuDownloader()
    return downloader.check_files_status()