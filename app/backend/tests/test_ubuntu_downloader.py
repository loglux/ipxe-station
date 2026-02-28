"""Tests for UbuntuDownloader."""

from pathlib import Path

import pytest

from app.backend.ubuntu_downloader import UbuntuDownloader


@pytest.fixture
def downloader(tmp_path):
    return UbuntuDownloader(base_path=str(tmp_path))


class TestUbuntuDownloaderInit:
    def test_default_base_path(self):
        dl = UbuntuDownloader()
        assert dl.base_path == Path("/srv/http")

    def test_custom_base_path(self, tmp_path):
        dl = UbuntuDownloader(base_path=str(tmp_path))
        assert dl.base_path == tmp_path

    def test_versions_dict_present(self, downloader):
        assert isinstance(downloader.versions, dict)
        assert len(downloader.versions) > 0

    def test_versions_contain_known_releases(self, downloader):
        assert "22.04" in downloader.versions
        assert "20.04" in downloader.versions

    def test_each_version_has_required_keys(self, downloader):
        for version, info in downloader.versions.items():
            assert "name" in info, f"{version} missing 'name'"
            assert "method" in info, f"{version} missing 'method'"


class TestGetUbuntuDir:
    def test_returns_versioned_subdir(self, downloader, tmp_path):
        path = downloader.get_ubuntu_dir("22.04")
        assert path == tmp_path / "ubuntu-22.04"

    def test_returns_path_object(self, downloader):
        path = downloader.get_ubuntu_dir("20.04")
        assert isinstance(path, Path)

    def test_all_versions_get_unique_dirs(self, downloader):
        dirs = {downloader.get_ubuntu_dir(v) for v in downloader.versions}
        assert len(dirs) == len(downloader.versions)


class TestGetInstalledVersions:
    def test_empty_base_returns_empty(self, downloader):
        result = downloader.get_installed_versions()
        assert result == []

    def test_nonexistent_base_returns_empty(self, tmp_path):
        dl = UbuntuDownloader(base_path=str(tmp_path / "nonexistent"))
        result = dl.get_installed_versions()
        assert result == []

    def test_dir_without_vmlinuz_not_counted(self, downloader, tmp_path):
        ubuntu_dir = tmp_path / "ubuntu-22.04"
        ubuntu_dir.mkdir()
        # No vmlinuz or initrd — should not be listed
        result = downloader.get_installed_versions()
        assert "22.04" not in result

    def test_complete_dir_counted(self, downloader, tmp_path):
        ubuntu_dir = tmp_path / "ubuntu-22.04"
        ubuntu_dir.mkdir()
        (ubuntu_dir / "vmlinuz").write_bytes(b"\x00")
        (ubuntu_dir / "initrd").write_bytes(b"\x00")

        result = downloader.get_installed_versions()
        assert "22.04" in result

    def test_multiple_versions_sorted_newest_first(self, downloader, tmp_path):
        for version in ["20.04", "22.04"]:
            ubuntu_dir = tmp_path / f"ubuntu-{version}"
            ubuntu_dir.mkdir()
            (ubuntu_dir / "vmlinuz").write_bytes(b"\x00")
            (ubuntu_dir / "initrd").write_bytes(b"\x00")

        result = downloader.get_installed_versions()
        assert result == sorted(result, reverse=True)

    def test_non_ubuntu_dirs_ignored(self, downloader, tmp_path):
        other_dir = tmp_path / "debian-12"
        other_dir.mkdir()
        (other_dir / "vmlinuz").write_bytes(b"\x00")
        (other_dir / "initrd").write_bytes(b"\x00")

        result = downloader.get_installed_versions()
        assert result == []


class TestDownloadUnsupportedVersion:
    def test_unsupported_version_returns_error_message(self, downloader):
        result = downloader.download_all_files(version="99.99")
        assert "Unsupported" in result or "❌" in result
