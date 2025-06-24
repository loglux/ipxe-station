from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs.status_tab import StatusTab
from app.ui_tabs.testing_tab import TestingTab
from app.ui_tabs.dhcp_tab import DHCPTab
from app.ui_tabs.ipxe_tab import iPXETab
from app.ui_tabs.ubuntu_tab import UbuntuTab
from app.ui_tabs.iso_tab import ISOTab
from app.ui_tabs.header import Header
from app.ui_tabs.footer import Footer
from app.ui_tabs.helpers import (
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
