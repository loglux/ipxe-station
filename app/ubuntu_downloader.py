# В методе download_ubuntu_files исправляем вызов:
def download_ubuntu_files(self, version: str = "22.04", progress=gr.Progress()) -> str:
    """Download Ubuntu files with progress tracking"""
    try:
        if not self.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        def progress_callback(current: int, total: int, filename: str):
            if total > 0:
                percent = (current / total) * 100
                progress(percent / 100, desc=f"Downloading {filename}")

        # ИСПРАВЛЕНО: используем правильный метод
        result = self.ubuntu_downloader.download_all_files(
            version=version,
            progress_callback=progress_callback
        )

        return result

    except Exception as e:
        return f"❌ Ubuntu download failed: {str(e)}"


def check_ubuntu_files(self) -> str:
    """Check Ubuntu files status"""
    try:
        if not self.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"
        return self.ubuntu_downloader.check_files_status()
    except Exception as e:
        return f"❌ Ubuntu check failed: {str(e)}"