"""
Common utilities for PXE Boot Station
Eliminates repetition across modules: ubuntu_downloader, iso_manager, system_status, etc.
"""

import functools
import ipaddress
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import requests

# =======================================
# FILE UTILITIES
# =======================================


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Used in: ubuntu_downloader.py, system_status.py, iso_manager.py
    Eliminates: ~45 lines of identical code
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.1f} {size_names[i]}"


def get_file_info(path: str) -> Dict[str, Any]:
    """
    Get comprehensive file information.

    Used in: ubuntu_downloader.py, system_status.py
    Eliminates: ~40 lines of identical code

    Returns:
        dict: File information including size, dates, permissions
    """
    file_path = Path(path)
    status = {
        "path": path,
        "exists": file_path.exists(),
        "size": 0,
        "size_human": "0 B",
        "modified": None,
        "readable": False,
    }

    if file_path.exists():
        try:
            stat = file_path.stat()
            status["size"] = stat.st_size
            status["size_human"] = format_file_size(stat.st_size)
            status["modified"] = datetime.fromtimestamp(stat.st_mtime)
            status["readable"] = os.access(path, os.R_OK)
        except Exception:
            pass

    return status


def ensure_directory(path: str | Path) -> Path:
    """
    Ensure directory exists, create if needed.

    Used in: ALL modules (ubuntu_downloader, iso_manager, dhcp_config, etc.)
    Eliminates: ~15 lines of repetitive mkdir calls

    Args:
        path: Directory path to ensure

    Returns:
        Path: Created directory path
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def safe_write_file(
    filepath: str | Path, content: str, encoding: str = "utf-8"
) -> Tuple[bool, str]:
    """
    Safely write content to file with directory creation.

    Used in: ubuntu_downloader.py, iso_manager.py, dhcp_config.py
    Eliminates: ~20 lines of repetitive file writing

    Args:
        filepath: Target file path
        content: Content to write
        encoding: File encoding

    Returns:
        tuple: (success, message)
    """
    try:
        file_path = Path(filepath)
        ensure_directory(file_path.parent)

        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)

        return True, f"✅ File saved to {filepath}"
    except Exception as e:
        return False, f"❌ Failed to save file: {str(e)}"


def safe_write_json(
    filepath: str | Path, data: Dict[str, Any], indent: int = 2
) -> Tuple[bool, str]:
    """
    Safely write JSON data to file.

    Used in: iso_manager.py, system_status.py
    Eliminates: ~15 lines of repetitive JSON writing

    Args:
        filepath: Target file path
        data: Data to write as JSON
        indent: JSON indentation

    Returns:
        tuple: (success, message)
    """
    try:
        file_path = Path(filepath)
        ensure_directory(file_path.parent)

        with open(file_path, "w") as f:
            json.dump(data, f, indent=indent, default=str)

        return True, f"✅ JSON saved to {filepath}"
    except Exception as e:
        return False, f"❌ Failed to save JSON: {str(e)}"


# =======================================
# DOWNLOAD UTILITIES
# =======================================


def download_with_progress(
    url: str,
    filepath: str,
    filename: str = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    timeout: Tuple[int, int] = (30, 300),
    chunk_size: int = 1024 * 1024,
) -> Tuple[bool, str]:
    """
    Download file with progress tracking.

    Used in: ubuntu_downloader.py, iso_manager.py
    Eliminates: ~60 lines of identical download code

    Args:
        url: Download URL
        filepath: Target file path
        filename: Display filename for progress
        progress_callback: Progress callback function
        timeout: (connect_timeout, read_timeout)
        chunk_size: Download chunk size in bytes

    Returns:
        tuple: (success, message)
    """
    try:
        if filename is None:
            filename = os.path.basename(filepath)

        # Make request
        response = requests.get(url, stream=True, timeout=timeout)
        if response.status_code != 200:
            return False, f"❌ Failed to download {filename}: HTTP {response.status_code}"

        # Get file size
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        # Ensure target directory exists
        ensure_directory(Path(filepath).parent)

        # Download with progress
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size, filename)

        # Verify download
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return False, f"❌ Download failed: {filename}"

        size_human = format_file_size(os.path.getsize(filepath))
        return True, f"✅ Downloaded {filename}: {size_human}"

    except Exception as e:
        return False, f"❌ Error downloading {filename}: {str(e)}"


# =======================================
# VALIDATION UTILITIES
# =======================================


def validate_ip_address(ip: str) -> Tuple[bool, str]:
    """
    Validate IPv4 address format.

    Used in: dhcp_config.py, system_status.py
    Eliminates: ~10 lines of validation code

    Args:
        ip: IP address string

    Returns:
        tuple: (is_valid, message)
    """
    try:
        ipaddress.IPv4Address(ip)
        return True, "Valid IP address"
    except ipaddress.AddressValueError:
        return False, f"Invalid IP address: {ip}"


def validate_string_field(
    value: str,
    field_name: str = "Field",
    min_length: int = 1,
    max_length: int = 255,
    allowed_chars: str = None,
) -> Tuple[bool, str]:
    """
    Validate string field with customizable rules.

    Used in: ipxe_manager.py, iso_manager.py, dhcp_config.py
    Eliminates: ~30 lines of similar validation patterns

    Args:
        value: String to validate
        field_name: Name for error messages
        min_length: Minimum length
        max_length: Maximum length
        allowed_chars: Regex pattern for allowed characters

    Returns:
        tuple: (is_valid, message)
    """
    if not value:
        return False, f"{field_name} cannot be empty"

    if len(value) < min_length:
        return False, f"{field_name} must be at least {min_length} characters"

    if len(value) > max_length:
        return False, f"{field_name} cannot exceed {max_length} characters"

    if allowed_chars:
        import re

        if not re.match(allowed_chars, value):
            return False, f"{field_name} contains invalid characters"

    return True, f"Valid {field_name.lower()}"


def validate_file_path(
    path: str, must_exist: bool = False, must_be_readable: bool = False
) -> Tuple[bool, str]:
    """
    Validate file path.

    Used in: Multiple modules for path validation
    Eliminates: ~20 lines of path checking code

    Args:
        path: File path to validate
        must_exist: Whether file must exist
        must_be_readable: Whether file must be readable

    Returns:
        tuple: (is_valid, message)
    """
    if not path:
        return False, "Path cannot be empty"

    try:
        file_path = Path(path)

        if must_exist and not file_path.exists():
            return False, f"File not found: {path}"

        if must_be_readable and file_path.exists() and not os.access(path, os.R_OK):
            return False, f"File not readable: {path}"

        return True, f"Valid path: {path}"

    except Exception as e:
        return False, f"Invalid path: {str(e)}"


# =======================================
# ERROR HANDLING DECORATORS
# =======================================


def safe_operation(error_prefix: str = "Operation", return_tuple: bool = False):
    """
    Decorator for safe operations with unified error handling.

    Used in: ALL modules for consistent error handling
    Eliminates: ~100 lines of try/catch patterns

    Args:
        error_prefix: Prefix for error messages
        return_tuple: If True, returns (success, message), else just message

    Usage:
        @safe_operation("File processing", return_tuple=True)
        def process_file(self, path):
            # operation logic
            return "Success message"
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)

                if return_tuple:
                    # If function returns tuple, pass through
                    if isinstance(result, tuple):
                        return result
                    # If function returns string, assume success
                    return True, result
                else:
                    return result

            except Exception as e:
                error_msg = f"❌ {error_prefix} failed: {str(e)}"
                if return_tuple:
                    return False, error_msg
                else:
                    return error_msg

        return wrapper

    return decorator


# =======================================
# METADATA UTILITIES
# =======================================


def create_metadata_dict(
    name: str,
    category: str = "general",
    source: str = "unknown",
    version: str = "1.0",
    **additional_fields,
) -> Dict[str, Any]:
    """
    Create standardized metadata dictionary.

    Used in: ubuntu_downloader.py, iso_manager.py
    Eliminates: ~20 lines of metadata creation code

    Args:
        name: Display name
        category: Item category
        source: Source URL or description
        version: Metadata format version
        **additional_fields: Additional metadata fields

    Returns:
        dict: Standardized metadata
    """
    metadata = {
        "name": name,
        "category": category,
        "source": source,
        "created": datetime.now().isoformat(),
        "modified": datetime.now().isoformat(),
        "format_version": version,
    }

    # Add additional fields
    metadata.update(additional_fields)

    return metadata


def save_metadata(
    directory: str | Path, metadata: Dict[str, Any], filename: str = "metadata.json"
) -> Tuple[bool, str]:
    """
    Save metadata to JSON file in specified directory.

    Used in: ubuntu_downloader.py, iso_manager.py
    Eliminates: ~15 lines of metadata saving code

    Args:
        directory: Target directory
        metadata: Metadata dictionary
        filename: Metadata filename

    Returns:
        tuple: (success, message)
    """
    metadata_path = Path(directory) / filename
    return safe_write_json(metadata_path, metadata)


def load_metadata(directory: str | Path, filename: str = "metadata.json") -> Dict[str, Any]:
    """
    Load metadata from JSON file.

    Used in: ubuntu_downloader.py, iso_manager.py
    Eliminates: ~10 lines of metadata loading code

    Args:
        directory: Source directory
        filename: Metadata filename

    Returns:
        dict: Metadata dictionary (empty if not found)
    """
    try:
        metadata_path = Path(directory) / filename
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                return json.load(f)
    except Exception:
        pass

    return {}


# =======================================
# SYSTEM UTILITIES
# =======================================


def get_cross_platform_path(unix_path: str, windows_path: str = None) -> str:
    """
    Get appropriate path for current operating system.

    Used in: Multiple modules for path handling
    Eliminates: ~15 lines of os.name checks

    Args:
        unix_path: Unix/Linux path
        windows_path: Windows path (defaults to C: version of unix_path)

    Returns:
        str: Platform-appropriate path
    """
    if os.name == "nt":  # Windows
        if windows_path:
            return windows_path
        # Convert unix path to windows (basic conversion)
        return unix_path.replace("/srv/", "C:/srv/").replace("/", "\\")
    else:  # Unix-like
        return unix_path


def calculate_total_size(directory: str | Path) -> int:
    """
    Calculate total size of all files in directory recursively.

    Used in: ubuntu_downloader.py, iso_manager.py, system_status.py
    Eliminates: ~15 lines of size calculation code

    Args:
        directory: Directory path

    Returns:
        int: Total size in bytes
    """
    total_size = 0
    try:
        for file_path in Path(directory).rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except Exception:
        pass

    return total_size


# =======================================
# CLEANUP UTILITIES
# =======================================


def safe_delete_directory(
    directory: str | Path, calculate_freed_space: bool = True
) -> Tuple[bool, str, int]:
    """
    Safely delete directory and calculate freed space.

    Used in: ubuntu_downloader.py, iso_manager.py
    Eliminates: ~20 lines of deletion code

    Args:
        directory: Directory to delete
        calculate_freed_space: Whether to calculate freed space

    Returns:
        tuple: (success, message, freed_bytes)
    """
    import shutil

    try:
        dir_path = Path(directory)

        if not dir_path.exists():
            return False, f"Directory does not exist: {directory}", 0

        # Calculate size before deletion
        freed_bytes = 0
        if calculate_freed_space:
            freed_bytes = calculate_total_size(dir_path)

        # Delete directory
        shutil.rmtree(dir_path)

        freed_size_human = format_file_size(freed_bytes)
        return True, f"✅ Directory deleted (freed {freed_size_human})", freed_bytes

    except Exception as e:
        return False, f"❌ Failed to delete directory: {str(e)}", 0


# =======================================
# EXPORT/IMPORT UTILITIES
# =======================================


def export_status_as_json(data: Dict[str, Any], pretty: bool = True) -> str:
    """
    Export status data as JSON string with proper serialization.

    Used in: system_status.py, ipxe_manager.py
    Eliminates: ~10 lines of JSON export code

    Args:
        data: Data to export
        pretty: Whether to format JSON prettily

    Returns:
        str: JSON string
    """

    def json_serializer(obj):
        """Handle datetime and other non-serializable objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    indent = 2 if pretty else None
    return json.dumps(data, indent=indent, default=json_serializer)
