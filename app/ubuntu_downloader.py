import requests
import tarfile
import tempfile
from pathlib import Path
import shutil


def download_ubuntu_netboot():
    """Download Ubuntu 24.04.2 LTS netboot files"""
    try:
        http_dir = Path("/srv/http/ubuntu")
        http_dir.mkdir(parents=True, exist_ok=True)

        status = "🔄 Downloading Ubuntu 24.04.2 LTS netboot...\n"

        # Ubuntu 24.04.2 netboot tarball URL
        netboot_url = "https://releases.ubuntu.com/noble/ubuntu-24.04.2-netboot-amd64.tar.gz"

        status += f"📥 Downloading netboot tarball (82 MB)...\n"

        # Download netboot tarball
        response = requests.get(netboot_url, timeout=300, stream=True)
        if response.status_code != 200:
            return f"❌ Failed to download netboot tarball: HTTP {response.status_code}"

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        status += "✅ Netboot tarball downloaded\n"
        status += "📦 Extracting netboot files...\n"

        # Extract tarball
        with tarfile.open(tmp_path, 'r:gz') as tar:
            # Find kernel and initrd files
            kernel_found = False
            initrd_found = False

            for member in tar.getmembers():
                # Look for kernel file (vmlinuz)
                if member.name.endswith('vmlinuz') or 'vmlinuz' in member.name:
                    with tar.extractfile(member) as kernel_file:
                        with open(http_dir / "vmlinuz", "wb") as f:
                            shutil.copyfileobj(kernel_file, f)
                    status += f"✅ Extracted kernel: {member.name}\n"
                    kernel_found = True

                # Look for initrd file
                elif member.name.endswith('initrd') or member.name.endswith('initrd.gz') or 'initrd' in member.name:
                    with tar.extractfile(member) as initrd_file:
                        with open(http_dir / "initrd", "wb") as f:
                            shutil.copyfileobj(initrd_file, f)
                    status += f"✅ Extracted initrd: {member.name}\n"
                    initrd_found = True

                # Stop when both files found
                if kernel_found and initrd_found:
                    break

        # Clean up temp file
        Path(tmp_path).unlink()

        # Create preseed file
        preseed_content = """# Ubuntu 24.04.2 Preseed Configuration
d-i debian-installer/locale string en_US
d-i console-setup/ask_detect boolean false
d-i keyboard-configuration/xkb-keymap select us

# Network configuration
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string ubuntu
d-i netcfg/get_domain string localdomain

# Mirror settings
d-i mirror/country string manual
d-i mirror/http/hostname string archive.ubuntu.com
d-i mirror/http/directory string /ubuntu
d-i mirror/http/proxy string

# Clock and time zone
d-i clock-setup/utc boolean true
d-i time/zone string UTC

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
tasksel tasksel/first multiselect ubuntu-desktop
d-i pkgsel/include string openssh-server
d-i pkgsel/upgrade select full-upgrade
d-i pkgsel/update-policy select unattended-upgrades

# Boot loader
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true

# Finish
d-i finish-install/reboot_in_progress note
"""

        with open(http_dir / "preseed.cfg", "w") as f:
            f.write(preseed_content)
        status += "✅ Preseed configuration created\n"

        # Check results
        errors = []
        if not kernel_found:
            errors.append("kernel")
        if not initrd_found:
            errors.append("initrd")

        if not errors:
            status += "\n🎉 Ubuntu 24.04.2 LTS netboot files ready!\n"
            status += "📝 Files: vmlinuz, initrd, preseed.cfg\n"
            status += "💾 Total size: ~82 MB extracted"
        else:
            status += f"\n❌ Ubuntu download failed! Missing: {', '.join(errors)}"

        return status

    except Exception as e:
        return f"❌ Error downloading Ubuntu netboot: {str(e)}"


def check_ubuntu_files():
    """Check if Ubuntu files exist and get their info"""
    http_dir = Path("/srv/http/ubuntu")

    files_info = []

    # Check kernel
    kernel_path = http_dir / "vmlinuz"
    if kernel_path.exists():
        size_mb = kernel_path.stat().st_size / (1024 * 1024)
        files_info.append(f"✅ vmlinuz ({size_mb:.1f} MB)")
    else:
        files_info.append("❌ vmlinuz (missing)")

    # Check initrd
    initrd_path = http_dir / "initrd"
    if initrd_path.exists():
        size_mb = initrd_path.stat().st_size / (1024 * 1024)
        files_info.append(f"✅ initrd ({size_mb:.1f} MB)")
    else:
        files_info.append("❌ initrd (missing)")

    # Check preseed
    preseed_path = http_dir / "preseed.cfg"
    if preseed_path.exists():
        size_kb = preseed_path.stat().st_size / 1024
        files_info.append(f"✅ preseed.cfg ({size_kb:.1f} KB)")
    else:
        files_info.append("❌ preseed.cfg (missing)")

    return "\n".join(files_info)