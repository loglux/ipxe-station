from app.backend.ipxe_menu.entry_model import iPXEEntry
from typing import List, Optional
from app.backend.config import PXE_SERVER_IP, NFS_ROOT


class MenuManager:
    def __init__(self):
        self.root_entries: List[iPXEEntry] = []

    def add_entry(self, entry: iPXEEntry, parent_id: Optional[str] = None):
        if parent_id is None:
            self.root_entries.append(entry)
        else:
            parent = self.find_entry_by_id(parent_id)
            if parent:
                entry.parent_id = parent_id
                parent.children.append(entry)

    def delete_entry(self, entry_id: str) -> bool:
        def _delete(entry_list: List[iPXEEntry], parent: Optional[iPXEEntry] = None):
            for entry in entry_list:
                if entry.id == entry_id:
                    if parent:
                        parent.children.remove(entry)
                    else:
                        self.root_entries.remove(entry)
                    return True
                if _delete(entry.children, entry):
                    return True
            return False

        return _delete(self.root_entries)

    def move_entry(self, entry_id: str, direction: str) -> bool:
        def _move(entry_list: List[iPXEEntry]) -> bool:
            for idx, entry in enumerate(entry_list):
                if entry.id == entry_id:
                    if direction == "up" and idx > 0:
                        entry_list[idx - 1], entry_list[idx] = entry_list[idx], entry_list[idx - 1]
                        return True
                    elif direction == "down" and idx < len(entry_list) - 1:
                        entry_list[idx + 1], entry_list[idx] = entry_list[idx], entry_list[idx + 1]
                        return True
            # Recursive search in subtrees
            for e in entry_list:
                if _move(e.children):
                    return True
            return False

        return _move(self.root_entries)

    def find_entry_by_id(self, entry_id: str) -> Optional[iPXEEntry]:
        def walk(entries: List[iPXEEntry]) -> Optional[iPXEEntry]:
            for entry in entries:
                if entry.id == entry_id:
                    return entry
                found = walk(entry.children)
                if found:
                    return found
            return None
        return walk(self.root_entries)

    def clear(self):
        self.root_entries.clear()

    def generate_script(self) -> str:
        lines = []

        def render_menu(entry: iPXEEntry, label: str):
            lines.append(f":{label}")
            for child in entry.children:
                lines.append(f"item {child.id} {child.label}")
            if entry.parent_id:
                lines.append(f"item back_{entry.id} Back")
            lines.append(f"choose selected || goto {label}")
            lines.append("goto ${selected}")
            lines.append("")

            for child in entry.children:
                if child.children:
                    render_menu(child, f"submenu_{child.id}")

        def render_command(entry: iPXEEntry):
            lines.append(f":{entry.id}")
            if entry.command:
                lines.append(f"    {entry.command}")
            elif entry.kernel:
                kernel_line = f"    kernel {entry.kernel}"
                if entry.cmdline:
                    kernel_line += f" {entry.cmdline}"
                lines.append(kernel_line)
                if entry.initrd:
                    lines.append(f"    initrd {entry.initrd}")
                if entry.imgargs:
                    lines.append(f"    imgargs {entry.imgargs}")
            else:
                lines.append(f"    echo No command or kernel specified")
            lines.append("    boot")
            lines.append("")

            if entry.parent_id:
                lines.append(f":back_{entry.id}")
                lines.append(f"    goto submenu_{entry.parent_id}")
                lines.append("")

        # Main menu
        lines.append(":start")
        for entry in self.root_entries:
            if entry.children:
                lines.append(f"item submenu_{entry.id} {entry.label}")
            else:
                lines.append(f"item {entry.id} {entry.label}")
        lines.append("choose selected || goto start")
        lines.append("goto ${selected}")
        lines.append("")

        # Submenus
        for entry in self.root_entries:
            if entry.children:
                render_menu(entry, f"submenu_{entry.id}")

        # Leaf commands and back entries
        def walk(entry: iPXEEntry):
            render_command(entry)
            for child in entry.children:
                walk(child)

        for entry in self.root_entries:
            walk(entry)

        return "\n".join(lines)

    @staticmethod
    def create_ubuntu_live_entry(id_suffix: str = "ubuntu") -> iPXEEntry:
        return iPXEEntry(
            id=f"ubuntu_{id_suffix}",
            label="Ubuntu Live",
            kernel=f"nfs://{PXE_SERVER_IP}:{NFS_ROOT}/ubuntu/casper/vmlinuz",
            initrd=f"nfs://{PXE_SERVER_IP}:{NFS_ROOT}/ubuntu/casper/initrd",
            cmdline=f"ip=dhcp boot=casper netboot=nfs nfsroot={PXE_SERVER_IP}:{NFS_ROOT}/ubuntu",
            imgargs="",
            command="",
            description="Boot into Ubuntu Live environment using NFS template"
        )

    @staticmethod
    def create_nfs_template_entry(id_suffix: str = "template") -> iPXEEntry:
        return iPXEEntry(
            id=f"nfs_{id_suffix}",
            label="NFS Boot Template",
            kernel=f"nfs://{PXE_SERVER_IP}:{NFS_ROOT}/krd/live/vmlinuz",
            initrd=f"nfs://{PXE_SERVER_IP}:{NFS_ROOT}/krd/live/initrd.img",
            cmdline="",
            imgargs=f"vmlinuz initrd=initrd.img boot=live components locales=en_US.UTF-8 netboot=nfs nfsroot={PXE_SERVER_IP}:{NFS_ROOT}/krd",
            command="",
            description="Boot template using NFS with placeholders"
        )
