"""Pydantic models for persisted iPXE menu configuration."""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class IpxeEntryModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=60)
    kernel: Optional[str] = None
    initrd: Optional[str] = None
    cmdline: str = ""
    description: str = ""
    enabled: bool = True
    order: int = 0
    entry_type: str = "boot"  # boot, menu, action, separator
    url: Optional[str] = None
    boot_mode: str = "netboot"
    requires_iso: bool = False
    requires_internet: bool = False

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
    server_ip: str = "localhost"
    http_port: int = 8000

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }

    @model_validator(mode="after")
    def check_default_entry(self):
        if self.default_entry:
            entry_names = [entry.name for entry in self.entries if entry.enabled]
            if self.default_entry not in entry_names:
                raise ValueError(f"Default entry '{self.default_entry}' not present in enabled entries")
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
    from app.backend.ipxe_manager import iPXEMenu, iPXEEntry

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
            )
            for entry in model.entries
        ],
        header_text=model.header_text,
        footer_text=model.footer_text,
        server_ip=model.server_ip,
        http_port=model.http_port,
    )
