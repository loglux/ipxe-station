"""Pydantic models for persisted iPXE menu configuration."""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class IpxeEntryModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=60)
    kernel: Optional[str] = None
    initrd: Optional[str] = None
    cmdline: Optional[str] = ""
    description: Optional[str] = ""
    enabled: bool = True
    order: int = 0
    entry_type: str = "boot"  # boot, menu, action, separator, chain, submenu
    url: Optional[str] = None
    boot_mode: Optional[str] = "netboot"
    requires_iso: bool = False
    requires_internet: bool = False
    parent: Optional[str] = None  # for submenu grouping
    preseed_profile: Optional[str] = None
    hiren_winpe_ready: bool = False
    hiren_bootmgr: Optional[str] = None
    hiren_bcd: Optional[str] = None
    hiren_boot_sdi: Optional[str] = None
    hiren_boot_wim: Optional[str] = None

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }


class IpxeMenuModel(BaseModel):
    title: str = Field("PXE Boot Station", min_length=1, max_length=80)
    timeout: int = 30000
    default_entry: Optional[str] = None
    entries: List[IpxeEntryModel] = Field(default_factory=list)
    header_text: str = ""
    footer_text: str = ""
    server_ip: str = ""  # filled by _apply_runtime_network_defaults from settings.json
    http_port: int = 0  # filled by _apply_runtime_network_defaults from settings.json

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }

    @model_validator(mode="after")
    def check_default_entry(self):
        if self.default_entry:
            entry_names = [entry.name for entry in self.entries if entry.enabled]
            if self.default_entry not in entry_names:
                raise ValueError(
                    f"Default entry '{self.default_entry}' not present in enabled entries"
                )
        return self


def menu_to_model(menu) -> IpxeMenuModel:
    """Convert iPXEMenu dataclass to Pydantic model."""
    return IpxeMenuModel(
        title=menu.title,
        timeout=menu.timeout,
        default_entry=menu.default_entry,
        entries=[
            IpxeEntryModel(
                name=entry.name,
                title=entry.title,
                kernel=entry.kernel,
                initrd=entry.initrd,
                cmdline=entry.cmdline,
                description=entry.description,
                enabled=entry.enabled,
                order=entry.order,
                entry_type=entry.entry_type,
                url=entry.url,
                boot_mode=entry.boot_mode,
                requires_iso=entry.requires_iso,
                requires_internet=entry.requires_internet,
                parent=entry.parent,
                preseed_profile=entry.preseed_profile,
                hiren_winpe_ready=entry.hiren_winpe_ready,
                hiren_bootmgr=entry.hiren_bootmgr,
                hiren_bcd=entry.hiren_bcd,
                hiren_boot_sdi=entry.hiren_boot_sdi,
                hiren_boot_wim=entry.hiren_boot_wim,
            )
            for entry in menu.entries
        ],
        header_text=menu.header_text,
        footer_text=menu.footer_text,
        server_ip=menu.server_ip,
        http_port=menu.http_port,
    )


def model_to_menu(model: IpxeMenuModel):
    """Convert Pydantic menu model to iPXEMenu dataclass."""
    from app.backend.ipxe_manager import iPXEEntry, iPXEMenu

    return iPXEMenu(
        title=model.title,
        timeout=model.timeout,
        default_entry=model.default_entry,
        entries=[
            iPXEEntry(
                name=entry.name,
                title=entry.title,
                kernel=entry.kernel,
                initrd=entry.initrd,
                cmdline=entry.cmdline,
                description=entry.description,
                enabled=entry.enabled,
                order=entry.order,
                entry_type=entry.entry_type,
                url=entry.url,
                boot_mode=entry.boot_mode,
                requires_iso=entry.requires_iso,
                requires_internet=entry.requires_internet,
                parent=entry.parent,
                preseed_profile=entry.preseed_profile,
                hiren_winpe_ready=entry.hiren_winpe_ready,
                hiren_bootmgr=entry.hiren_bootmgr,
                hiren_bcd=entry.hiren_bcd,
                hiren_boot_sdi=entry.hiren_boot_sdi,
                hiren_boot_wim=entry.hiren_boot_wim,
            )
            for entry in model.entries
        ],
        header_text=model.header_text,
        footer_text=model.footer_text,
        server_ip=model.server_ip,
        http_port=model.http_port,
    )
