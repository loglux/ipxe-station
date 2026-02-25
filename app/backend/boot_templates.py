BOOT_TEMPLATES = {
    "Ubuntu Live": {
        "kernel": "ubuntu/casper/vmlinuz",
        "initrd": "ubuntu/casper/initrd",
        "cmdline": "boot=casper netboot=nfs nfsroot=${server_ip}:/srv/ubuntu",
        "imgargs": "",
    },
    "Windows PE (WIMBoot)": {
        "kernel": "wimboot",
        "initrd": "bootmgr BCD boot.sdi boot.wim",
        "cmdline": "",
        "imgargs": "",
    },
    "UEFI HTTP Boot": {
        "kernel": "efi/boot/bootx64.efi",
        "initrd": "",
        "cmdline": "",
        "imgargs": "",
    },
}
