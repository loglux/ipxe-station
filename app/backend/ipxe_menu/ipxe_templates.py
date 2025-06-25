# File: backend/ipxe_menu/ipxe_templates.py
from app.backend.ipxe_menu.entry_model import iPXEEntry

from jinja2 import Environment, FileSystemLoader
import os

template_dir = os.path.join(os.path.dirname(__file__), "jinja_templates")
env = Environment(loader=FileSystemLoader(template_dir))

def render_ipxe_template(template_name: str, variables: dict) -> str:
    template = env.get_template(template_name)
    return template.render(variables)


def create_ubuntu_live_entry(id_suffix: str = "ubuntu") -> iPXEEntry:
    return iPXEEntry(
        id=f"ubuntu_{id_suffix}",
        label="Ubuntu Live",
        kernel="nfs://${server}:${nfs_root}/ubuntu/casper/vmlinuz",
        initrd="nfs://${server}:${nfs_root}/ubuntu/casper/initrd",
        cmdline="ip=dhcp boot=casper netboot=nfs nfsroot=${server}:${nfs_root}/ubuntu",
        imgargs="",
        command="",
        description="Boot into Ubuntu Live environment using NFS template"
    )


def create_nfs_template_entry(id_suffix: str = "template") -> iPXEEntry:
    return iPXEEntry(
        id=f"nfs_{id_suffix}",
        label="NFS Boot Template",
        kernel="nfs://${server}:${nfs_root}/krd/live/vmlinuz",
        initrd="nfs://${server}:${nfs_root}/krd/live/initrd.img",
        cmdline="",
        imgargs="vmlinuz initrd=initrd.img boot=live components locales=en_US.UTF-8 netboot=nfs nfsroot=${server}:${nfs_root}/krd",
        command="",
        description="Boot template using NFS with placeholders"
    )
