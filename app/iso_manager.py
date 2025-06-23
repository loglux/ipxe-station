"""
ISO Management for PXE Boot Station
Handles ISO download, upload, and management for various operating systems and utilities
"""

import requests
import shutil
import tempfile
import json
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
                              progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Download ISO from URL with progress tracking"""
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
                iso_dir, display_name, category, url, filename
            )
            status += metadata_result + "\n"

            # Final size check
            iso_size_gb = iso_path.stat().st_size / (1024 ** 3)
            status += f"💾 Final size: {iso_size_gb:.2f} GB\n"
            status += f"✅ ISO download completed successfully!"

            return status

        except Exception as e:
            return f"❌ Error downloading ISO: {str(e)}"

    def upload_iso_file(self, file_obj, folder_name: str, display_name: str,
                        category: str = "custom") -> str:
        """Upload ISO file from local system"""
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
            filename = file_obj.name if hasattr(file_obj, 'name') else f"{folder_name}.iso"
            if not filename.endswith('.iso'):
                filename += '.iso'

            iso_path = iso_dir / filename

            # Copy file content
            with open(iso_path, "wb") as f:
                if hasattr(file_obj, 'read'):
                    shutil.copyfileobj(file_obj, f)
                else:
                    f.write(file_obj)

            status += f"💾 File saved as: {filename}\n"

            # Check file size
            iso_size_gb = iso_path.stat().st_size / (1024 ** 3)
            status += f"📊 File size: {iso_size_gb:.2f} GB\n"

            # Create metadata
            metadata_result = self._create_metadata(
                iso_dir, display_name, category, "uploaded", filename
            )
            status += metadata_result + "\n"

            status += "✅ ISO upload completed successfully!"
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
                         source_url: str, filename: str) -> str:
        """Create metadata file for ISO"""
        try:
            metadata = {
                "display_name": display_name,
                "category": category,
                "source_url": source_url,
                "filename": filename,
                "created": datetime.now().isoformat(),
                "format_version": "1.0"
            }

            metadata_file = iso_dir / 'metadata.json'
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            return f"📋 Metadata created: {metadata_file.name}"

        except Exception as e:
            return f"⚠️ Failed to create metadata: {str(e)}"

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

        # Find ISO files
        iso_files = list(iso_dir.glob('*.iso'))
        if not iso_files:
            status_lines.append("❌ No ISO files found")
            return "\n".join(status_lines)

        # Load metadata
        metadata_file = iso_dir / 'metadata.json'
        metadata = self._load_metadata(metadata_file)

        # Display metadata if available
        if metadata:
            status_lines.append(f"📋 **Display Name:** {metadata.get('display_name', 'Unknown')}")
            status_lines.append(f"🏷️ **Category:** {metadata.get('category', 'Unknown')}")
            status_lines.append(f"🌐 **Source:** {metadata.get('source_url', 'Unknown')}")

        # Show ISO files
        for iso_file in iso_files:
            size_gb = iso_file.stat().st_size / (1024 ** 3)
            mod_time = datetime.fromtimestamp(iso_file.stat().st_mtime)
            status_lines.append(f"💿 **{iso_file.name}** ({size_gb:.2f} GB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")

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