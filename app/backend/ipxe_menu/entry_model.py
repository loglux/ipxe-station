# backend/ipxe_menu/entry_model.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class iPXEEntry:
    id: str
    label: str
    command: Optional[str] = None
    goto_label: Optional[str] = None
    children: List["iPXEEntry"] = field(default_factory=list)
    parent_id: Optional[str] = None
    is_back_item: bool = False
    kernel: Optional[str] = None
    initrd: Optional[str] = None
    cmdline: Optional[str] = None
    imgargs: Optional[str] = None
    description: Optional[str] = None
