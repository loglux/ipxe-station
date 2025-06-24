from .base_tab import PXEBootStationUI
from .status_tab import StatusTab
from .testing_tab import TestingTab
from .dhcp_tab import DHCPTab
from .ipxe_tab import iPXETab
from .ubuntu_tab import UbuntuTab
from .iso_tab import ISOTab
from .header import Header
from .footer import Footer
from .helpers import (
    safe_method,
    _create_action_buttons,
    _create_status_textbox
)


TAB_REGISTRY = [
    StatusTab,
    TestingTab,
    DHCPTab,
    iPXETab,
    UbuntuTab,
    ISOTab,
]

HEADER_FOOTER_COMPONENTS = [Header, Footer]

__all__ = [
    'PXEBootStationUI',
    'StatusTab',
    'DHCPTab',
    'iPXETab',
    'UbuntuTab',
    'ISOTab',
    'TestingTab',
    'Header',
    'Footer',
    'TAB_REGISTRY',
    'safe_method',
    '_create_action_buttons',
    '_create_status_textbox'
]
