"""Tests for ISOManager."""

from pathlib import Path

import pytest

from app.backend.iso_manager import ISOManager


@pytest.fixture
def tmp_iso_manager(tmp_path):
    """ISOManager backed by a temporary directory."""
    return ISOManager(base_path=str(tmp_path))


class TestISOManagerInit:
    def test_default_base_path(self):
        mgr = ISOManager()
        assert mgr.base_path == Path("/srv/http")

    def test_custom_base_path(self, tmp_path):
        mgr = ISOManager(base_path=str(tmp_path))
        assert mgr.base_path == tmp_path

    def test_categories_defined(self, tmp_iso_manager):
        assert "antivirus" in tmp_iso_manager.categories
        assert "utilities" in tmp_iso_manager.categories
        assert "recovery" in tmp_iso_manager.categories
        assert "linux" in tmp_iso_manager.categories
        assert "windows" in tmp_iso_manager.categories
        assert "custom" in tmp_iso_manager.categories


class TestGetIsoDir:
    def test_valid_name(self, tmp_iso_manager, tmp_path):
        path = tmp_iso_manager.get_iso_dir("kaspersky")
        assert path == tmp_path / "kaspersky"

    def test_sanitises_special_chars(self, tmp_iso_manager, tmp_path):
        path = tmp_iso_manager.get_iso_dir("ubuntu 22.04")
        # Spaces and dots become underscores
        assert path.parent == tmp_path
        assert ".." not in str(path)

    def test_empty_name_raises(self, tmp_iso_manager):
        with pytest.raises(ValueError, match="empty"):
            tmp_iso_manager.get_iso_dir("")

    def test_whitespace_only_raises(self, tmp_iso_manager):
        with pytest.raises(ValueError, match="empty"):
            tmp_iso_manager.get_iso_dir("   ")

    def test_path_traversal_sanitised(self, tmp_iso_manager, tmp_path):
        # Dots and slashes are sanitised, resulting path stays within base_path
        path = tmp_iso_manager.get_iso_dir("../../../etc")
        resolved = path.resolve()
        # The path must remain under the base directory
        assert str(resolved).startswith(str(tmp_path.resolve()))

    def test_path_stays_within_base(self, tmp_iso_manager, tmp_path):
        path = tmp_iso_manager.get_iso_dir("safe-dir")
        resolved = path.resolve()
        assert str(resolved).startswith(str(tmp_path.resolve()))

    def test_hyphen_and_underscore_allowed(self, tmp_iso_manager, tmp_path):
        path = tmp_iso_manager.get_iso_dir("my-iso_v2")
        assert path == tmp_path / "my-iso_v2"


class TestListExistingISOs:
    def test_empty_base_returns_empty_list(self, tmp_iso_manager):
        result = tmp_iso_manager.list_existing_isos()
        assert result == []

    def test_nonexistent_base_returns_empty_list(self, tmp_path):
        mgr = ISOManager(base_path=str(tmp_path / "nonexistent"))
        result = mgr.list_existing_isos()
        assert result == []

    def test_directory_without_iso_ignored(self, tmp_iso_manager, tmp_path):
        (tmp_path / "no-iso-here").mkdir()
        (tmp_path / "no-iso-here" / "readme.txt").write_text("hello")
        result = tmp_iso_manager.list_existing_isos()
        assert result == []

    def test_directory_with_iso_included(self, tmp_iso_manager, tmp_path):
        iso_dir = tmp_path / "my-distro"
        iso_dir.mkdir()
        (iso_dir / "my-distro.iso").write_bytes(b"\x00" * 1024)

        result = tmp_iso_manager.list_existing_isos()
        assert len(result) == 1
        assert result[0]["folder_name"] == "my-distro"
        assert result[0]["filename"] == "my-distro.iso"

    def test_ubuntu_dirs_skipped(self, tmp_iso_manager, tmp_path):
        ubuntu_dir = tmp_path / "ubuntu-22.04"
        ubuntu_dir.mkdir()
        (ubuntu_dir / "ubuntu-22.04.iso").write_bytes(b"\x00" * 1024)

        result = tmp_iso_manager.list_existing_isos()
        assert result == []

    def test_iso_info_has_required_keys(self, tmp_iso_manager, tmp_path):
        iso_dir = tmp_path / "rescue"
        iso_dir.mkdir()
        (iso_dir / "rescue.iso").write_bytes(b"\x00" * 512)

        result = tmp_iso_manager.list_existing_isos()
        assert len(result) == 1
        iso = result[0]
        assert "folder_name" in iso
        assert "display_name" in iso
        assert "category" in iso
        assert "filename" in iso
        assert "size_gb" in iso
        assert "has_metadata" in iso
