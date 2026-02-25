"""
Backend Package for PXE Boot Station
Contains all business logic, services, and utilities
Separated from UI components for better architecture
"""

# Import all backend modules for easy access
try:
    from .utils import *
except ImportError:
    pass

try:
    from .ubuntu_downloader import UbuntuDownloader
except ImportError:
    UbuntuDownloader = None

try:
    from .ipxe_manager import iPXEEntry, iPXEManager, iPXEMenu, iPXETemplateManager
except ImportError:
    iPXEManager = None
    iPXEMenu = None
    iPXEEntry = None
    iPXETemplateManager = None

try:
    from .dhcp_config import DHCPConfig, DHCPConfigManager, create_simple_config
except ImportError:
    DHCPConfigManager = None
    DHCPConfig = None
    create_simple_config = None

try:
    from .iso_manager import ISOManager
except ImportError:
    ISOManager = None

try:
    from .system_status import SystemStatusManager, get_system_status
except ImportError:
    SystemStatusManager = None
    get_system_status = None

try:
    from .tests import SystemTester
except ImportError:
    SystemTester = None

try:
    from .file_utils import FileManager
except ImportError:
    FileManager = None

# Export main classes for easy import
__all__ = [
    # Main service classes
    "UbuntuDownloader",
    "iPXEManager",
    "iPXEMenu",
    "iPXEEntry",
    "iPXETemplateManager",
    "DHCPConfigManager",
    "DHCPConfig",
    "ISOManager",
    "SystemStatusManager",
    "SystemTester",
    "FileManager",
    # Helper functions
    "create_simple_config",
    "get_system_status",
]


def get_available_services():
    """
    Get status of all backend services.

    Returns:
        dict: Service name -> availability status
    """
    return {
        "ubuntu_downloader": UbuntuDownloader is not None,
        "ipxe_manager": iPXEManager is not None,
        "dhcp_manager": DHCPConfigManager is not None,
        "iso_manager": ISOManager is not None,
        "system_status": SystemStatusManager is not None,
        "system_tester": SystemTester is not None,
        "file_manager": FileManager is not None,
    }


def validate_backend():
    """
    Validate that all backend services are available.

    Returns:
        tuple: (all_available, missing_services)
    """
    services = get_available_services()
    missing = [name for name, available in services.items() if not available]
    return len(missing) == 0, missing
