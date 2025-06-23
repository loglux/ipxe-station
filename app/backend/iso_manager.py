"""
ISO Management for PXE Boot Station
Handles ISO download, upload, and management for various operating systems and utilities
REFACTORED: Using common utilities to eliminate repetition
"""

import shutil
import subprocess
from pathlib import Path
import os
import re
from typing import Callable, Optional, Dict, Any, List
from datetime import datetime

# Import common utilities to eliminate repetition
from utils import (
    format_file_size,
    download_with_progress,
    safe_operation,
    ensure_directory,
    calculate_total_size,
    safe_delete_directory,
    create_metadata_dict,
    save_metadata,
    load_metadata,
    validate_string_field
)


class ISOManager:
    """ISO file manager for PXE Boot Station"""

    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = "/srv/http"  # Docker standard

        self.base_path = Path(base_path)

        # Supported categories for organization
        self.categories = {
            "antivirus": "Antivirus & Security",
            "utilities": "System Utilities",
            "recovery": "Recovery & Rescue",
            "linux": "Linux Distributions",
            "windows": "Windows Images",
            "custom": "Custom Images"
        }

    def get_iso_dir(self, folder_name: str) -> Path:
        """Get directory path for specific ISO folder"""
        # Sanitize folder name
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', folder_name)
        return self.base_path / safe_name

    @safe_operation("ISO download")
    def download_iso_from_url(self, url: str, folder_name: str, display_name: str,
                              category: str = "custom",
                              extract_files: bool = False,
                              iso_retention: str = "keep",
                              progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download ISO from URL with optional file extraction"""

        # Validate inputs using common utility
        validation_checks = [
            (url.strip(), "URL"),
            (folder_name.strip(), "Folder name"),
            (display_name.strip(), "Display name")
        ]

        for value, field_name in validation_checks:
            is_valid, message = validate_string_field(value, field_name)
            if not is_valid:
                return message

        # Create target directory
        iso_dir = self.get_iso_dir(folder_name)
        ensure_directory(iso_dir)

        status = f"🔄 Downloading {display_name}...\n"
        status += f"📁 Target directory: {iso_dir}\n"
        status += f"🌐 URL: {url}\n"

        # Get filename from URL or use default
        try:
            filename = url.split('/')[-1]
            if not filename.endswith('.iso'):
                filename = f"{folder_name}.iso"
        except:
            filename = f"{folder_name}.iso"

        iso_path = iso_dir / filename

        # Download with progress tracking using common utility
        success, download_result = download_with_progress(
            url=url,
            filepath=str(iso_path),
            filename=filename,
            progress_callback=progress_callback
        )

        status += download_result + "\n"

        if not success:
            return status

        # Create metadata using common utility
        metadata_result = self._create_metadata(
            iso_dir, display_name, category, url, filename, extract_files, iso_retention
        )
        status += metadata_result + "\n"

        # Extract boot files if requested
        if extract_files:
            status += "📦 Extracting boot files from ISO...\n"
            extract_result = self._extract_boot_files(iso_path, iso_dir, iso_retention)
            status += extract_result + "\n"

        # Final size check using common utility
        total_size = calculate_total_size(iso_dir)
        final_size_human = format_file_size(total_size)
        status += f"💾 Total folder size: {final_size_human}\n"
        status += f"✅ ISO processing completed successfully!"

        return status

    @safe_operation("ISO upload")
    def upload_iso_file(self, file_obj, folder_name: str, display_name: str,
                        category: str = "custom",
                        extract_files: bool = False,
                        iso_retention: str = "keep") -> str:
        """Upload ISO file from local system with optional file extraction"""

        if not file_obj:
            return "❌ No file provided"

        # Validate inputs using common utility
        validation_checks = [
            (folder_name.strip(), "Folder name"),
            (display_name.strip(), "Display name")
        ]

        for value, field_name in validation_checks:
            is_valid, message = validate_string_field(value, field_name)
            if not is_valid:
                return message

        # Create target directory
        iso_dir = self.get_iso_dir(folder_name)
        ensure_directory(iso_dir)

        status = f"📁 Uploading {display_name}...\n"
        status += f"📂 Target directory: {iso_dir}\n"

        # Save uploaded file
        filename = None

        # Handle different file object types from Gradio
        if isinstance(file_obj, str):
            # Gradio passes file path as string
            source_path = file_obj
            filename = os.path.basename(source_path)
        elif hasattr(file_obj, 'name') and isinstance(file_obj.name, str):
            # File object with name attribute (path)
            source_path = file_obj.name
            filename = os.path.basename(source_path)
        elif hasattr(file_obj, 'read'):
            # File-like object with read method
            source_path = None
            filename = getattr(file_obj, 'name', f"{folder_name}.iso")
        else:
            return "❌ Unsupported file object type"

        # Ensure filename ends with .iso
        if not filename.endswith('.iso'):
            filename += '.iso'

        iso_path = iso_dir / filename

        # Copy file content based on type
        if source_path:
            # Copy from file path
            shutil.copy2(source_path, iso_path)
        else:
            # Copy from file-like object
            with open(iso_path, "wb") as f:
                shutil.copyfileobj(file_obj, f)

        status += f"💾 File saved as: {filename}\n"

        # Check file size using common utility
        iso_size_human = format_file_size(iso_path.stat().st_size)
        status += f"📊 File size: {iso_size_human}\n"

        # Create metadata using common utility
        metadata_result = self._create_metadata(
            iso_dir, display_name, category, "uploaded", filename, extract_files, iso_retention
        )
        status += metadata_result + "\n"

        # Extract boot files if requested
        if extract_files:
            status += "📦 Extracting boot files from ISO...\n"
            extract_result = self._extract_boot_files(iso_path, iso_dir, iso_retention)
            status += extract_result + "\n"

        # Final size check using common utility
        total_size = calculate_total_size(iso_dir)
        final_size_human = format_file_size(total_size)
        status += f"💾 Total folder size: {final_size_human}\n"
        status += "✅ ISO processing completed successfully!"

        return status

    def list_existing_isos(self) -> List[Dict[str, Any]]:
        """Scan and return list of existing ISOs with metadata"""
        isos = []

        try:
            if not self.base_path.exists():
                return isos

            # Scan all directories in base path
            for item in self.base_path.iterdir():
                if not item.is_dir():
                    continue

                # Skip Ubuntu directories (managed separately)
                if item.name.startswith('ubuntu-'):
                    continue

                # Look for ISO files
                iso_files = list(item.glob('*.iso'))
                if not iso_files:
                    continue

                # Load metadata using common utility
                metadata = load_metadata(item)

                # Get largest ISO file if multiple
                main_iso = max(iso_files, key=lambda f: f.stat().st_size)

                iso_info = {
                    "folder_name": item.name,
                    "display_name": metadata.get("name", item.name),
                    "category": metadata.get("category", "custom"),
                    "source_url": metadata.get("source", "unknown"),
                    "filename": main_iso.name,
                    "file_path": str(main_iso),
                    "size_gb": main_iso.stat().st_size / (1024 ** 3),
                    "created": datetime.fromtimestamp(main_iso.stat().st_ctime),
                    "modified": datetime.fromtimestamp(main_iso.stat().st_mtime),
                    "iso_count": len(iso_files),
                    "has_metadata": (item / "metadata.json").exists()
                }

                isos.append(iso_info)

            # Sort by creation date (newest first)
            isos.sort(key=lambda x: x['created'], reverse=True)

        except Exception:
            # Return empty list on error
            pass

        return isos

    def get_iso_status(self, folder_name: str = None) -> str:
        """Get detailed status of ISOs"""
        if folder_name:
            # Check specific ISO
            return self._get_single_iso_status(folder_name)
        else:
            # Check all ISOs
            return self._get_all_isos_status()

    def delete_iso(self, folder_name: str) -> str:
        """Delete ISO and its directory"""
        iso_dir = self.get_iso_dir(folder_name)

        if not iso_dir.exists():
            return f"ℹ️ ISO folder '{folder_name}' does not exist"

        # Use common utility for safe deletion
        success, message, freed_bytes = safe_delete_directory(iso_dir)

        if success:
            return f"✅ ISO '{folder_name}' deleted - {message}"

        return f"❌ Error deleting ISO '{folder_name}': {message}"

    def get_categories(self) -> Dict[str, str]:
        """Get available categories for ISOs"""
        return self.categories

    def get_summary(self) -> str:
        """Get brief summary of ISO management for UI"""
        isos = self.list_existing_isos()

        summary = []
        summary.append("📊 **ISO Images Overview**")

        if not isos:
            summary.append("📁 No ISOs installed yet")
            summary.append("⬆️ Use the forms above to download or upload ISO images")
            return "\n".join(summary)

        # Count by category and extraction status
        by_category = {}
        total_size = 0
        extracted_count = 0

        for iso in isos:
            category = iso['category']
            if category not in by_category:
                by_category[category] = 0
            by_category[category] += 1
            total_size += iso['size_gb']

            # Check if files were extracted
            iso_dir = self.get_iso_dir(iso['folder_name'])
            if (iso_dir / "vmlinuz").exists() or (iso_dir / "initrd").exists():
                extracted_count += 1

        summary.append(f"📁 Total ISOs: {len(isos)}")
        summary.append(f"💾 Total size: {total_size:.1f} GB")
        summary.append(f"🏷️ Categories: {len(by_category)}")
        summary.append(f"📦 With extracted files: {extracted_count}")

        # Show by category
        if by_category:
            summary.append("\n📋 **By Category:**")
            for cat, count in by_category.items():
                cat_name = self.categories.get(cat, cat.title())
                summary.append(f"  • {cat_name}: {count} ISO(s)")

        return "\n".join(summary)

    def get_folder_names(self) -> List[str]:
        """Get list of existing ISO folder names for dropdowns"""
        isos = self.list_existing_isos()
        if not isos:
            return ["No ISOs found"]

        # Return folder names sorted alphabetically
        folders = [iso["folder_name"] for iso in isos]
        return sorted(folders)

    def get_iso_retention_options(self) -> Dict[str, str]:
        """Get available ISO retention options"""
        return {
            "keep": "Keep in same folder",
            "subfolder": "Move to iso/ subfolder",
            "delete": "Delete after extraction"
        }

    @safe_operation("Metadata creation")
    def _create_metadata(self, iso_dir: Path, display_name: str, category: str,
                         source_url: str, filename: str, extract_files: bool = False,
                         iso_retention: str = "keep") -> str:
        """Create metadata file for ISO using common utility"""

        metadata = create_metadata_dict(
            name=display_name,
            category=category,
            source=source_url,
            filename=filename,
            extract_files=extract_files,
            iso_retention=iso_retention,
            version="1.1"
        )

        success, message = save_metadata(iso_dir, metadata)
        return f"📋 Metadata created" if success else message

    @safe_operation("Boot files extraction")
    def _extract_boot_files(self, iso_path: Path, iso_dir: Path, iso_retention: str) -> str:
        """Extract boot files from ISO using 7-zip"""
        status = ""
        extract_temp_dir = f"/tmp/extract-{iso_dir.name}"

        # Create temporary extraction directory
        ensure_directory(extract_temp_dir)

        # Extract ISO with 7-zip
        cmd = ['7z', 'x', str(iso_path), f'-o{extract_temp_dir}', '-y']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return f"❌ 7-Zip extraction failed: {result.stderr}"

        status += "✅ ISO extracted successfully\n"

        # Find and copy boot files
        boot_files_found = self._find_and_copy_boot_files(extract_temp_dir, iso_dir)
        status += boot_files_found + "\n"

        # Handle ISO retention
        iso_handling_result = self._handle_iso_retention(iso_path, iso_dir, iso_retention)
        status += iso_handling_result + "\n"

        # Cleanup temporary directory
        try:
            shutil.rmtree(extract_temp_dir)
            status += "🧹 Temporary extraction directory cleaned up\n"
        except:
            pass

        return status

    @safe_operation("Boot files search and copy")
    def _find_and_copy_boot_files(self, extract_dir: str, target_dir: Path) -> str:
        """Find and copy boot files from extracted ISO"""
        status = ""
        files_found = 0

        # Common boot file patterns for different types of ISOs
        boot_patterns = [
            # Linux rescue disks
            ("casper/vmlinuz", "vmlinuz"),
            ("casper/initrd", "initrd"),
            ("casper/initrd.lz", "initrd"),
            ("live/vmlinuz", "vmlinuz"),
            ("live/initrd", "initrd"),
            ("isolinux/vmlinuz", "vmlinuz"),
            ("isolinux/initrd.img", "initrd"),
            # Generic patterns
            ("boot/vmlinuz*", "vmlinuz"),
            ("boot/initrd*", "initrd"),
            ("*/vmlinuz*", "vmlinuz"),
            ("*/initrd*", "initrd"),
        ]

        # Search for boot files using patterns
        for pattern, target_name in boot_patterns:
            if "*" in pattern:
                # Use glob for wildcard patterns
                import glob
                matches = glob.glob(os.path.join(extract_dir, pattern))
                if matches:
                    # Use first match
                    source_file = matches[0]
                    target_file = target_dir / target_name
                    shutil.copy2(source_file, target_file)
                    status += f"✅ Extracted {target_name}: {os.path.basename(source_file)}\n"
                    files_found += 1
                    continue
            else:
                # Direct file check
                source_file = os.path.join(extract_dir, pattern)
                if os.path.exists(source_file):
                    target_file = target_dir / target_name
                    shutil.copy2(source_file, target_file)
                    status += f"✅ Extracted {target_name}: {pattern}\n"
                    files_found += 1
                    continue

        # Look for config files
        config_patterns = [
            "isolinux/isolinux.cfg",
            "boot/grub/grub.cfg",
            "syslinux/syslinux.cfg",
            "*/menu.cfg"
        ]

        for pattern in config_patterns:
            if "*" in pattern:
                import glob
                matches = glob.glob(os.path.join(extract_dir, pattern))
                if matches:
                    source_file = matches[0]
                    target_file = target_dir / f"config.cfg"
                    shutil.copy2(source_file, target_file)
                    status += f"✅ Extracted config: {os.path.basename(source_file)}\n"
                    files_found += 1
                    break
            else:
                source_file = os.path.join(extract_dir, pattern)
                if os.path.exists(source_file):
                    target_file = target_dir / f"config.cfg"
                    shutil.copy2(source_file, target_file)
                    status += f"✅ Extracted config: {pattern}\n"
                    files_found += 1
                    break

        # Copy additional useful directories
        for dirname in ("live", "casper", "boot"):
            source_dir = Path(extract_dir) / dirname
            if source_dir.is_dir():
                shutil.copytree(source_dir,
                                target_dir / dirname,
                                dirs_exist_ok=True)
                status += f"✅ Extracted directory: {dirname}/\n"
                files_found += 1

        if files_found == 0:
            status += "⚠️ No recognizable boot files found in ISO\n"
            # List some files for debugging
            try:
                all_files = []
                for root, dirs, files in os.walk(extract_dir):
                    for file in files[:5]:  # First 5 files only
                        rel_path = os.path.relpath(os.path.join(root, file), extract_dir)
                        all_files.append(rel_path)
                status += f"🔍 Sample files in ISO: {', '.join(all_files[:10])}\n"
            except:
                pass
        else:
            status += f"📊 Total boot files extracted: {files_found}"

        return status

    @safe_operation("ISO retention handling")
    def _handle_iso_retention(self, iso_path: Path, iso_dir: Path, iso_retention: str) -> str:
        """Handle ISO file based on retention policy"""
        if iso_retention == "delete":
            iso_path.unlink()
            return f"🗑️ Original ISO deleted to save space"

        elif iso_retention == "subfolder":
            iso_subdir = iso_dir / "iso"
            ensure_directory(iso_subdir)
            new_iso_path = iso_subdir / iso_path.name
            shutil.move(str(iso_path), str(new_iso_path))
            return f"📁 ISO moved to iso/ subfolder: {new_iso_path.name}"

        elif iso_retention == "keep":
            return f"💾 Original ISO kept: {iso_path.name}"

        else:
            return f"⚠️ Unknown retention policy: {iso_retention}"

    def _get_single_iso_status(self, folder_name: str) -> str:
        """Get status for single ISO"""
        iso_dir = self.get_iso_dir(folder_name)

        if not iso_dir.exists():
            return f"❌ ISO folder '{folder_name}' not found"

        status_lines = []
        status_lines.append(f"📁 **{folder_name}** - {iso_dir}")

        # Load metadata using common utility
        metadata = load_metadata(iso_dir)

        # Display metadata if available
        if metadata:
            status_lines.append(f"📋 **Display Name:** {metadata.get('name', 'Unknown')}")
            status_lines.append(f"🏷️ **Category:** {metadata.get('category', 'Unknown')}")
            status_lines.append(f"🌐 **Source:** {metadata.get('source', 'Unknown')}")

            # Show extraction info
            if metadata.get('extract_files'):
                status_lines.append(f"📦 **Extraction:** Enabled")
                status_lines.append(f"💾 **ISO Retention:** {metadata.get('iso_retention', 'unknown')}")

        # Find ISO files
        iso_files = list(iso_dir.glob('*.iso'))
        iso_subdir = iso_dir / "iso"
        if iso_subdir.exists():
            iso_files.extend(list(iso_subdir.glob('*.iso')))

        if iso_files:
            status_lines.append(f"\n💿 **ISO Files:**")
            for iso_file in iso_files:
                size_human = format_file_size(iso_file.stat().st_size)
                mod_time = datetime.fromtimestamp(iso_file.stat().st_mtime)
                relative_path = iso_file.relative_to(iso_dir)
                status_lines.append(
                    f"  • **{relative_path}** ({size_human}) - {mod_time.strftime('%Y-%m-%d %H:%M')}")

        # Check for extracted boot files
        boot_files = ["vmlinuz", "initrd", "config.cfg"]
        extracted_files = []

        for boot_file in boot_files:
            file_path = iso_dir / boot_file
            if file_path.exists():
                size_human = format_file_size(file_path.stat().st_size)
                extracted_files.append(f"{boot_file} ({size_human})")

        if extracted_files:
            status_lines.append(f"\n📦 **Extracted Boot Files:**")
            for file_info in extracted_files:
                status_lines.append(f"  • {file_info}")

        # Check for extracted directories
        for dirname in ("live", "casper", "boot"):
            extracted_subdir = iso_dir / dirname
            if extracted_subdir.exists():
                status_lines.append(f"\n📂 **Extracted Directories:**")
                status_lines.append(f"  • {dirname}/")
                break

        # Show boot options available
        status_lines.append(f"\n🚀 **Boot Options Available:**")

        if any(f.exists() for f in [iso_dir / "vmlinuz", iso_dir / "initrd"]):
            status_lines.append(f"  • ⚡ Fast boot (extracted files)")

        if iso_files:
            status_lines.append(f"  • 💿 Full ISO boot (sanboot/imgfetch)")

        if not iso_files and not extracted_files:
            status_lines.append(f"  • ❌ No boot options available")

        return "\n".join(status_lines)

    def _get_all_isos_status(self) -> str:
        """Get status for all ISOs"""
        isos = self.list_existing_isos()

        if not isos:
            return f"📁 No ISOs found in {self.base_path}\n\n🔍 Use the upload/download forms above to add ISOs"

        status_lines = []
        status_lines.append(f"📁 ISO Images in {self.base_path}")
        status_lines.append("=" * 50)

        total_size = 0
        by_category = {}

        for iso in isos:
            category = iso['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(iso)
            total_size += iso['size_gb']

        # Group by category
        for category, category_isos in by_category.items():
            category_name = self.categories.get(category, category.title())
            status_lines.append(f"\n🏷️ **{category_name}**")

            for iso in category_isos:
                status_lines.append(f"  💿 **{iso['display_name']}**")
                status_lines.append(f"     📁 Folder: {iso['folder_name']}")
                status_lines.append(f"     💾 Size: {iso['size_gb']:.2f} GB")
                status_lines.append(f"     📅 Created: {iso['created'].strftime('%Y-%m-%d %H:%M')}")

        # Summary
        status_lines.append(f"\n📊 **SUMMARY**")
        status_lines.append(f"📁 Total ISOs: {len(isos)}")
        status_lines.append(f"💾 Total size: {total_size:.2f} GB")
        status_lines.append(f"🏷️ Categories: {', '.join(by_category.keys())}")

        return "\n".join(status_lines)


# Legacy functions for backward compatibility
def download_iso(url: str, folder_name: str, display_name: str) -> str:
    """Legacy function - download ISO file"""
    manager = ISOManager()
    return manager.download_iso_from_url(url, folder_name, display_name)


def list_isos() -> List[Dict[str, Any]]:
    """Legacy function - list ISO files"""
    manager = ISOManager()
    return manager.list_existing_isos()