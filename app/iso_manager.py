"""
ISO Management for PXE Boot Station
Handles ISO download, upload, and management for various operating systems and utilities
"""

import requests
import shutil
import tempfile
import json
import subprocess
import glob
from pathlib import Path
import os
import re
from typing import Callable, Optional, Dict, Any, List
from datetime import datetime


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

    def download_iso_from_url(self, url: str, folder_name: str, display_name: str,
                              category: str = "custom",
                              extract_files: bool = False,
                              iso_retention: str = "keep",
                              progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download ISO from URL with optional file extraction

        Args:
            url: Download URL
            folder_name: Target folder name
            display_name: Display name for UI
            category: ISO category
            extract_files: Whether to extract boot files from ISO
            iso_retention: What to do with ISO after extraction ("delete", "keep", "subfolder")
            progress_callback: Progress callback function
        """
        try:
            # Validate inputs
            if not url.strip():
                return "❌ URL cannot be empty"

            if not folder_name.strip():
                return "❌ Folder name cannot be empty"

            if not display_name.strip():
                return "❌ Display name cannot be empty"

            # Create target directory
            iso_dir = self.get_iso_dir(folder_name)
            iso_dir.mkdir(parents=True, exist_ok=True)

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

            # Download with progress tracking
            download_result = self._download_file_with_progress(
                url, str(iso_path), filename, progress_callback
            )
            status += download_result + "\n"

            if "✅" not in download_result:
                return status

            # Create metadata file
            metadata_result = self._create_metadata(
                iso_dir, display_name, category, url, filename, extract_files, iso_retention
            )
            status += metadata_result + "\n"

            # Extract boot files if requested
            if extract_files:
                status += "📦 Extracting boot files from ISO...\n"
                extract_result = self._extract_boot_files(iso_path, iso_dir, iso_retention)
                status += extract_result + "\n"

            # Final size check and summary
            total_size = 0
            for file_path in iso_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            final_size_gb = total_size / (1024 ** 3)
            status += f"💾 Total folder size: {final_size_gb:.2f} GB\n"
            status += f"✅ ISO processing completed successfully!"

            return status

        except Exception as e:
            return f"❌ Error downloading ISO: {str(e)}"

    def upload_iso_file(self, file_obj, folder_name: str, display_name: str,
                        category: str = "custom",
                        extract_files: bool = False,
                        iso_retention: str = "keep") -> str:
        """Upload ISO file from local system with optional file extraction

        Args:
            file_obj: File object from upload
            folder_name: Target folder name
            display_name: Display name for UI
            category: ISO category
            extract_files: Whether to extract boot files from ISO
            iso_retention: What to do with ISO after extraction ("delete", "keep", "subfolder")
        """
        try:
            # Validate inputs
            if not file_obj:
                return "❌ No file provided"

            if not folder_name.strip():
                return "❌ Folder name cannot be empty"

            if not display_name.strip():
                return "❌ Display name cannot be empty"

            # Create target directory
            iso_dir = self.get_iso_dir(folder_name)
            iso_dir.mkdir(parents=True, exist_ok=True)

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

            # Check file size
            iso_size_gb = iso_path.stat().st_size / (1024 ** 3)
            status += f"📊 File size: {iso_size_gb:.2f} GB\n"

            # Create metadata
            metadata_result = self._create_metadata(
                iso_dir, display_name, category, "uploaded", filename, extract_files, iso_retention
            )
            status += metadata_result + "\n"

            # Extract boot files if requested
            if extract_files:
                status += "📦 Extracting boot files from ISO...\n"
                extract_result = self._extract_boot_files(iso_path, iso_dir, iso_retention)
                status += extract_result + "\n"

            # Final size check and summary
            total_size = 0
            for file_path in iso_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            final_size_gb = total_size / (1024 ** 3)
            status += f"💾 Total folder size: {final_size_gb:.2f} GB\n"
            status += "✅ ISO processing completed successfully!"
            return status

        except Exception as e:
            return f"❌ Error uploading ISO: {str(e)}"

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

                # Load metadata if exists
                metadata_file = item / 'metadata.json'
                metadata = self._load_metadata(metadata_file)

                # Get largest ISO file if multiple
                main_iso = max(iso_files, key=lambda f: f.stat().st_size)

                iso_info = {
                    "folder_name": item.name,
                    "display_name": metadata.get("display_name", item.name),
                    "category": metadata.get("category", "custom"),
                    "source_url": metadata.get("source_url", "unknown"),
                    "filename": main_iso.name,
                    "file_path": str(main_iso),
                    "size_gb": main_iso.stat().st_size / (1024 ** 3),
                    "created": datetime.fromtimestamp(main_iso.stat().st_ctime),
                    "modified": datetime.fromtimestamp(main_iso.stat().st_mtime),
                    "iso_count": len(iso_files),
                    "has_metadata": metadata_file.exists()
                }

                isos.append(iso_info)

            # Sort by creation date (newest first)
            isos.sort(key=lambda x: x['created'], reverse=True)

        except Exception as e:
            # Return empty list on error
            pass

        return isos

    def get_iso_status(self, folder_name: str = None) -> str:
        """Get detailed status of ISOs"""
        try:
            if folder_name:
                # Check specific ISO
                return self._get_single_iso_status(folder_name)
            else:
                # Check all ISOs
                return self._get_all_isos_status()

        except Exception as e:
            return f"❌ Error checking ISO status: {str(e)}"

    def delete_iso(self, folder_name: str) -> str:
        """Delete ISO and its directory"""
        try:
            iso_dir = self.get_iso_dir(folder_name)

            if not iso_dir.exists():
                return f"ℹ️ ISO folder '{folder_name}' does not exist"

            # Calculate total size before deletion
            total_size = 0
            for file_path in iso_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            # Remove directory
            shutil.rmtree(iso_dir)

            size_gb = total_size / (1024 ** 3)
            return f"✅ ISO '{folder_name}' deleted (freed {size_gb:.2f} GB)"

        except Exception as e:
            return f"❌ Error deleting ISO: {str(e)}"

    def get_categories(self) -> Dict[str, str]:
        """Get available categories for ISOs"""
        return self.categories

    def get_summary(self) -> str:
        """Get brief summary of ISO management for UI"""
        try:
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

        except Exception as e:
            return f"❌ Error getting summary: {str(e)}"

    def get_folder_names(self) -> List[str]:
        """Get list of existing ISO folder names for dropdowns"""
        try:
            isos = self.list_existing_isos()
            if not isos:
                return ["No ISOs found"]

            # Return folder names sorted alphabetically
            folders = [iso["folder_name"] for iso in isos]
            return sorted(folders)

        except Exception as e:
            return ["Error loading ISOs"]

    def _download_file_with_progress(self, url: str, filepath: str, filename: str,
                                     progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download file with progress tracking"""
        try:
            response = requests.get(url, stream=True, timeout=(30, 300))
            if response.status_code != 200:
                return f"❌ Failed to download {filename}: HTTP {response.status_code}"

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            # Use 1MB chunks for large files
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

            size_gb = os.path.getsize(filepath) / (1024 ** 3)
            return f"✅ Downloaded {filename}: {size_gb:.2f} GB"

        except Exception as e:
            return f"❌ Error downloading {filename}: {str(e)}"

    def _create_metadata(self, iso_dir: Path, display_name: str, category: str,
                         source_url: str, filename: str, extract_files: bool = False,
                         iso_retention: str = "keep") -> str:
        """Create metadata file for ISO"""
        try:
            metadata = {
                "display_name": display_name,
                "category": category,
                "source_url": source_url,
                "filename": filename,
                "extract_files": extract_files,
                "iso_retention": iso_retention,
                "created": datetime.now().isoformat(),
                "format_version": "1.1"
            }

            metadata_file = iso_dir / 'metadata.json'
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            return f"📋 Metadata created: {metadata_file.name}"

        except Exception as e:
            return f"⚠️ Failed to create metadata: {str(e)}"

    def _extract_boot_files(self, iso_path: Path, iso_dir: Path, iso_retention: str) -> str:
        """Extract boot files from ISO using 7-zip"""
        try:
            status = ""
            extract_temp_dir = f"/tmp/extract-{iso_dir.name}"

            # Create temporary extraction directory
            os.makedirs(extract_temp_dir, exist_ok=True)

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

        except subprocess.TimeoutExpired:
            return "❌ ISO extraction timed out (>5 minutes)"
        except Exception as e:
            return f"❌ Error extracting ISO: {str(e)}"

    def _find_and_copy_boot_files(self, extract_dir: str, target_dir: Path) -> str:
        """Find and copy boot files from extracted ISO"""
        try:
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
            # useful_dirs = ["live", "casper", "boot"]
            # extracted_dir = target_dir / "extracted"
            #
            # for dir_name in useful_dirs:
            #     source_dir = os.path.join(extract_dir, dir_name)
            #     if os.path.exists(source_dir):
            #         target_subdir = extracted_dir / dir_name
            #         target_subdir.mkdir(parents=True, exist_ok=True)
            #         shutil.copytree(source_dir, target_subdir, dirs_exist_ok=True)
            #         status += f"✅ Extracted directory: {dir_name}/\n"
            #         files_found += 1
            # Removed 'extracted' directory
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

        except Exception as e:
            return f"❌ Error finding boot files: {str(e)}"

    def _handle_iso_retention(self, iso_path: Path, iso_dir: Path, iso_retention: str) -> str:
        """Handle ISO file based on retention policy"""
        try:
            if iso_retention == "delete":
                iso_path.unlink()
                return f"🗑️ Original ISO deleted to save space"

            elif iso_retention == "subfolder":
                iso_subdir = iso_dir / "iso"
                iso_subdir.mkdir(exist_ok=True)
                new_iso_path = iso_subdir / iso_path.name
                shutil.move(str(iso_path), str(new_iso_path))
                return f"📁 ISO moved to iso/ subfolder: {new_iso_path.name}"

            elif iso_retention == "keep":
                return f"💾 Original ISO kept: {iso_path.name}"

            else:
                return f"⚠️ Unknown retention policy: {iso_retention}"

        except Exception as e:
            return f"❌ Error handling ISO retention: {str(e)}"

    def get_iso_retention_options(self) -> Dict[str, str]:
        """Get available ISO retention options"""
        return {
            "keep": "Keep in same folder",
            "subfolder": "Move to iso/ subfolder",
            "delete": "Delete after extraction"
        }

    def _load_metadata(self, metadata_file: Path) -> Dict[str, Any]:
        """Load metadata from JSON file"""
        try:
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _get_single_iso_status(self, folder_name: str) -> str:
        """Get status for single ISO"""
        iso_dir = self.get_iso_dir(folder_name)

        if not iso_dir.exists():
            return f"❌ ISO folder '{folder_name}' not found"

        status_lines = []
        status_lines.append(f"📁 **{folder_name}** - {iso_dir}")

        # Load metadata
        metadata_file = iso_dir / 'metadata.json'
        metadata = self._load_metadata(metadata_file)

        # Display metadata if available
        if metadata:
            status_lines.append(f"📋 **Display Name:** {metadata.get('display_name', 'Unknown')}")
            status_lines.append(f"🏷️ **Category:** {metadata.get('category', 'Unknown')}")
            status_lines.append(f"🌐 **Source:** {metadata.get('source_url', 'Unknown')}")

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
                size_gb = iso_file.stat().st_size / (1024 ** 3)
                mod_time = datetime.fromtimestamp(iso_file.stat().st_mtime)
                relative_path = iso_file.relative_to(iso_dir)
                status_lines.append(
                    f"  • **{relative_path}** ({size_gb:.2f} GB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")

        # Check for extracted boot files
        boot_files = ["vmlinuz", "initrd", "config.cfg"]
        extracted_files = []

        for boot_file in boot_files:
            file_path = iso_dir / boot_file
            if file_path.exists():
                size_mb = file_path.stat().st_size / (1024 ** 2)
                extracted_files.append(f"{boot_file} ({size_mb:.1f} MB)")

        if extracted_files:
            status_lines.append(f"\n📦 **Extracted Boot Files:**")
            for file_info in extracted_files:
                status_lines.append(f"  • {file_info}")

        # Check for extracted directories
        extracted_dir = iso_dir / "extracted"
        if extracted_dir.exists():
            subdirs = [d.name for d in extracted_dir.iterdir() if d.is_dir()]
            if subdirs:
                status_lines.append(f"\n📂 **Extracted Directories:**")
                for subdir in subdirs:
                    status_lines.append(f"  • {subdir}/")

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