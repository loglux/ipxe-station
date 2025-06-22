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
import subprocess
from typing import Callable, Optional, Dict, Any
from datetime import datetime


class UbuntuDownloader:
    """Ubuntu files downloader optimized for Docker environment"""

    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = "/srv/http"  # Docker standard

        self.base_path = Path(base_path)
        self.ubuntu_dir = self.base_path / "ubuntu"

        # Conf For Docker
        self.versions = {
            "24.04": {
                "name": "Ubuntu 24.04.2 LTS (Noble)",
                "method": "iso_extract",
                "iso_url": "https://releases.ubuntu.com/noble/ubuntu-24.04.2-live-server-amd64.iso",
                "size_mb": 2800
            },
            "22.04": {
                "name": "Ubuntu 22.04.5 LTS (Jammy)",
                "method": "iso_extract",
                "iso_url": "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-live-server-amd64.iso",
                "size_mb": 2400
            },
            "20.04": {
                "name": "Ubuntu 20.04.6 LTS (Focal)",
                "method": "netboot",
                "netboot_url": "http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/netboot.tar.gz",
                "size_mb": 35
            }
        }

    def download_all_files(self, version: str = "20.04",
                           progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download Ubuntu files - Docker optimized"""
        try:
            if version not in self.versions:
                return f"❌ Unsupported Ubuntu version: {version}"

            version_info = self.versions[version]

            # Create directory
            self.ubuntu_dir.mkdir(parents=True, exist_ok=True)

            status = f"🔄 Downloading {version_info['name']}...\n"

            # Выбираем метод
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
        """Download and extract ISO - Docker optimized with system tools"""
        try:
            version_info = self.versions[version]
            iso_url = version_info["iso_url"]

            status = f"📥 Downloading Ubuntu ISO ({version_info['size_mb']} MB)...\n"

            # Download ISO
            iso_path = f"/tmp/ubuntu-{version}.iso"
            download_result = self._download_file_fast(iso_url, iso_path, f"ubuntu-{version}.iso", progress_callback)
            status += download_result + "\n"

            if "✅" not in download_result:
                return status

            status += "📦 Extracting files from ISO using 7-Zip...\n"

            # Extract using 7-zip (быстро и надежно)
            extract_result = self._extract_iso_with_7zip(iso_path, version)
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

    def _download_file_fast(self, url: str, filepath: str, filename: str,
                            progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Fast download with proper chunking for large files"""
        try:
            # Use requests with optimized settings
            response = requests.get(url, stream=True, timeout=(30, 300))  # 30s connect, 5min read
            if response.status_code != 200:
                return f"❌ Failed to download {filename}: HTTP {response.status_code}"

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            # Larger chunks for big files (1MB)
            chunk_size = 1024 * 1024

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size, filename)

            # Verify download
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                return f"❌ Download failed: {filename}"

            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            return f"✅ Downloaded {filename}: {size_mb:.1f} MB"

        except Exception as e:
            return f"❌ Error downloading {filename}: {str(e)}"

    def _extract_iso_with_7zip(self, iso_path: str, version: str) -> str:
        """Extract ISO using 7-zip - fast and reliable"""
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
                    # Copy files
                    shutil.copy2(kernel_path, self.ubuntu_dir / "vmlinuz")
                    shutil.copy2(initrd_path, self.ubuntu_dir / "initrd")

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
                # List available files for debugging
                status += "❌ Could not find kernel/initrd files\n"
                try:
                    available_files = []
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            if any(pattern in file.lower() for pattern in ['vmlinuz', 'linux', 'initrd', 'kernel']):
                                rel_path = os.path.relpath(os.path.join(root, file), extract_dir)
                                available_files.append(rel_path)
                    status += f"🔍 Available files: {available_files[:10]}\n"
                except:
                    pass

            return status

        except subprocess.TimeoutExpired:
            return "❌ 7-Zip extraction timed out (>5 minutes)"
        except Exception as e:
            return f"❌ Error extracting ISO: {str(e)}"

    # ... the other methods remain unchanged (netboot, preseed, check_files) ...

    def _download_and_extract_iso(self, version: str,
                                  progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download ISO and extract kernel/initrd for modern Ubuntu versions"""
        try:
            version_info = self.versions[version]
            iso_url = version_info["iso_url"]

            status = f"📥 Downloading Ubuntu ISO ({version_info['size_mb']} MB)...\n"
            status += "⚠️  This will take some time due to large file size\n"

            # Download ISO to temp location
            temp_iso = tempfile.NamedTemporaryFile(delete=False, suffix='.iso')

            response = requests.get(iso_url, timeout=600, stream=True)
            if response.status_code != 200:
                return f"❌ Failed to download ISO: HTTP {response.status_code}"

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with temp_iso as f:
                for chunk in response.iter_content(chunk_size=32768):  # Larger chunks for big files
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size, f"ubuntu-{version}.iso")

            status += "✅ ISO downloaded\n"
            status += "📦 Extracting kernel and initrd from ISO...\n"

            # Extract files from ISO
            extract_result = self._extract_from_iso(temp_iso.name, version)
            status += extract_result

            # Clean up
            Path(temp_iso.name).unlink()

            return status

        except Exception as e:
            return f"❌ Error downloading ISO: {str(e)}"

    def _extract_from_iso(self, iso_path: str, version: str) -> str:
        """Extract kernel and initrd from Ubuntu ISO"""
        try:
            import subprocess
            import platform

            status = ""

            # Mount point for ISO
            if platform.system() == "Windows":
                # На Windows можем использовать 7zip или другие инструменты
                status += "⚠️  ISO extraction on Windows requires manual setup\n"
                status += "🔧 Please extract casper/vmlinuz and casper/initrd from ISO manually\n"
                return status

            # На Linux используем mount
            mount_point = tempfile.mkdtemp()

            try:
                # Mount ISO
                mount_cmd = ["sudo", "mount", "-o", "loop", iso_path, mount_point]
                result = subprocess.run(mount_cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    return f"❌ Failed to mount ISO: {result.stderr}"

                status += f"✅ ISO mounted at {mount_point}\n"

                # Look for kernel and initrd in common locations
                possible_paths = [
                    ("casper/vmlinuz", "casper/initrd"),  # Live images
                    ("install/vmlinuz", "install/initrd.gz"),  # Installer
                    ("casper/vmlinuz.efi", "casper/initrd.lz"),  # EFI variants
                ]

                kernel_found = False
                initrd_found = False

                for kernel_path, initrd_path in possible_paths:
                    kernel_source = Path(mount_point) / kernel_path
                    initrd_source = Path(mount_point) / initrd_path

                    if kernel_source.exists() and initrd_source.exists():
                        # Copy kernel
                        shutil.copy2(kernel_source, self.ubuntu_dir / "vmlinuz")
                        status += f"✅ Extracted kernel: {kernel_path}\n"
                        kernel_found = True

                        # Copy initrd
                        shutil.copy2(initrd_source, self.ubuntu_dir / "initrd")
                        status += f"✅ Extracted initrd: {initrd_path}\n"
                        initrd_found = True

                        break

                if not (kernel_found and initrd_found):
                    # List available files for debugging
                    try:
                        files = list(Path(mount_point).rglob("*"))
                        relevant_files = [f for f in files if any(pattern in f.name.lower()
                                                                  for pattern in
                                                                  ['vmlinuz', 'linux', 'initrd', 'initramfs'])]
                        status += f"🔍 Available files: {[str(f.relative_to(mount_point)) for f in relevant_files[:10]]}\n"
                    except:
                        pass

            finally:
                # Unmount
                subprocess.run(["sudo", "umount", mount_point], capture_output=True)
                os.rmdir(mount_point)

            if kernel_found and initrd_found:
                status += "🎉 Successfully extracted kernel and initrd from ISO!\n"
            else:
                status += "❌ Could not find kernel and initrd in ISO\n"

            return status

        except Exception as e:
            return f"❌ Error extracting from ISO: {str(e)}"

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