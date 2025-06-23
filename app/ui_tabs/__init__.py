"""
UI Tabs module for PXE Boot Station
Exports all tab classes for use in main UI builder
"""

# Import base class
from .base_tab import BaseTab

# Import all tab implementations
from .status_tab import StatusTab
from .testing_tab import TestingTab
from .dhcp_tab import DHCPTab
from .ipxe_tab import iPXETab
from .ubuntu_tab import UbuntuTab
from .iso_tab import ISOTab

# Export all available tabs
__all__ = [
    'BaseTab',
    'StatusTab',
    'TestingTab',
    'DHCPTab',
    'iPXETab',
    'UbuntuTab',
    'ISOTab',
]

# Tab registry for automatic loading (Variant 1 approach)
AVAILABLE_TABS = [
    StatusTab,
    TestingTab,
    DHCPTab,
    iPXETab,
    UbuntuTab,
    ISOTab,
]

# Tab metadata for configuration and validation
TAB_METADATA = {
    'StatusTab': {
        'name': '📊 System Status',
        'description': 'System health and resource monitoring',
        'dependencies': ['status_manager'],
        'order': 1
    },
    'TestingTab': {
        'name': '🧪 System Testing',
        'description': 'TFTP, HTTP and system component testing',
        'dependencies': ['system_tester'],
        'order': 2
    },
    'DHCPTab': {
        'name': '🌐 DHCP Configuration',
        'description': 'DHCP server configuration generation',
        'dependencies': ['dhcp_manager'],
        'order': 3
    },
    'iPXETab': {
        'name': '📋 iPXE Menu',
        'description': 'iPXE boot menu configuration and management',
        'dependencies': ['ipxe_manager'],
        'order': 4
    },
    'UbuntuTab': {
        'name': '🐧 Ubuntu Download',
        'description': 'Ubuntu files download and management',
        'dependencies': ['ubuntu_downloader'],
        'order': 5
    },
    'ISOTab': {
        'name': '📁 ISO Management',
        'description': 'ISO images download, upload and management',
        'dependencies': ['iso_manager'],
        'order': 6
    }
}


def get_available_tabs():
    """
    Get list of available tab classes.

    Returns:
        List of tab classes that are currently implemented
    """
    return AVAILABLE_TABS.copy()


def get_tab_metadata(tab_name: str = None):
    """
    Get metadata for specific tab or all tabs.

    Args:
        tab_name: Name of specific tab, None for all tabs

    Returns:
        Tab metadata dictionary
    """
    if tab_name:
        return TAB_METADATA.get(tab_name, {})
    return TAB_METADATA.copy()


def validate_tab_dependencies(ui_controller):
    """
    Validate that all required dependencies are available for tabs.

    Args:
        ui_controller: Main UI controller instance

    Returns:
        Dictionary with validation results for each tab
    """
    results = {}

    for tab_class in AVAILABLE_TABS:
        tab_name = tab_class.__name__
        metadata = TAB_METADATA.get(tab_name, {})
        dependencies = metadata.get('dependencies', [])

        missing_deps = []
        for dep in dependencies:
            if not getattr(ui_controller, dep, None):
                missing_deps.append(dep)

        results[tab_name] = {
            'available': len(missing_deps) == 0,
            'missing_dependencies': missing_deps,
            'error_message': f"Missing: {', '.join(missing_deps)}" if missing_deps else None
        }

    return results