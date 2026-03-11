/**
 * scenarios.js - Central definition of all boot scenarios
 *
 * This is the heart of the new architecture: instead of forcing users to understand
 * iPXE technical details (entry_type, boot_mode, etc.), we provide high-level scenarios
 * that automatically configure all necessary fields.
 */

export const SCENARIOS = {
  // ========== LINUX DISTRIBUTIONS ==========

  ubuntu_netboot: {
    id: 'ubuntu_netboot',
    displayName: 'Ubuntu Netboot',
    description: 'Network installation of Ubuntu (requires internet)',
    icon: '🐧',
    category: 'linux',

    // Automatically generated fields (hidden from user)
    generated: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      requires_internet: true,
      requires_iso: false,
    },

    // Which fields to show in the form
    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent', 'entry_type', 'boot_mode'],
    },

    // Default template values
    template: () => ({
      cmdline: `ip=dhcp url=http://\${server_ip}:\${port}/ubuntu-\${version}/`,
    }),

    // Asset detection configuration
    assetDiscovery: {
      pattern: 'ubuntu-*/vmlinuz',
      requiredFiles: ['vmlinuz', 'initrd'],
      versionExtractor: /ubuntu-(\d+\.\d+)/,
    },

    // Auto-download URLs for popular versions
    downloadUrls: {
      '22.04': {
        name: 'Ubuntu 22.04.5 LTS',
        iso: 'https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso',
        extractFiles: {
          kernel: 'casper/vmlinuz',
          initrd: 'casper/initrd',
        },
        size: '2.8 GB',
      },
      '24.04': {
        name: 'Ubuntu 24.04.4 LTS',
        iso: 'https://releases.ubuntu.com/24.04/ubuntu-24.04.4-live-server-amd64.iso',
        extractFiles: {
          kernel: 'casper/vmlinuz',
          initrd: 'casper/initrd',
        },
        size: '2.9 GB',
      },
    },

    // Help text for users
    help: `
      Ubuntu Netboot downloads the system from the internet during installation.

      Requirements:
      - Internet connection
      - Kernel and initrd files

      The installer will download packages during installation.
    `,
  },

  ubuntu_live: {
    id: 'ubuntu_live',
    displayName: 'Ubuntu Live (ISO)',
    description: 'Boot from ISO file (no internet required)',
    icon: '💿',
    category: 'linux',

    generated: {
      entry_type: 'boot',
      boot_mode: 'live',
      requires_internet: false,
      requires_iso: true,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent', 'entry_type', 'boot_mode'],
    },

    template: () => ({
      cmdline: `ip=dhcp boot=casper url=http://\${server_ip}:\${port}/http/ubuntu-\${version}/ubuntu-\${version}-live-server-amd64.iso`,
    }),

    assetDiscovery: {
      pattern: 'ubuntu-*/*.iso',
      requiredFiles: ['vmlinuz', 'initrd', '*.iso'],
      versionExtractor: /ubuntu-(\d+\.\d+)/,
    },

    downloadUrls: {
      '22.04': {
        name: 'Ubuntu 22.04.5 LTS Desktop',
        iso: 'https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso',
        extractFiles: {
          kernel: 'casper/vmlinuz',
          initrd: 'casper/initrd',
        },
        size: '4.7 GB',
      },
      '24.04': {
        name: 'Ubuntu 24.04.4 LTS Desktop',
        iso: 'https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso',
        extractFiles: {
          kernel: 'casper/vmlinuz',
          initrd: 'casper/initrd',
        },
        size: '5.8 GB',
      },
    },

    help: `
      Ubuntu Live boots the full desktop environment from an ISO file.

      Requirements:
      - ISO file on server
      - Kernel and initrd extracted from ISO

      No internet required after files are downloaded.
    `,
  },

  ubuntu_preseed: {
    id: 'ubuntu_preseed',
    displayName: 'Ubuntu Preseed (Automated)',
    description: 'Automated installation with preseed configuration',
    icon: '🤖',
    category: 'linux',

    generated: {
      entry_type: 'boot',
      boot_mode: 'preseed',
      requires_internet: true,
      requires_iso: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd', 'cmdline'],
      optional: ['description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: `ip=dhcp auto=true priority=critical url=http://\${server_ip}:\${port}/preseed.cfg`,
    }),

    help: `
      Preseed enables fully automated Ubuntu installation.

      You need to create a preseed.cfg file with installation settings.
    `,
  },

  debian_netboot: {
    id: 'debian_netboot',
    displayName: 'Debian Netboot',
    description: 'Network installation of Debian',
    icon: '🌀',
    category: 'linux',

    generated: {
      entry_type: 'boot',
      boot_mode: 'netboot',
      requires_internet: true,
      requires_iso: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: `ip=dhcp`,
    }),

    assetDiscovery: {
      pattern: 'debian-*/linux',
      requiredFiles: ['linux', 'initrd.gz'],
      versionExtractor: /debian-(\d+)/,
    },

    downloadUrls: {
      '12': {
        name: 'Debian 12 (Bookworm)',
        kernel: 'https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux',
        initrd: 'https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz',
        size: '50 MB',
      },
      '11': {
        name: 'Debian 11 (Bullseye)',
        kernel: 'https://deb.debian.org/debian/dists/bullseye/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux',
        initrd: 'https://deb.debian.org/debian/dists/bullseye/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz',
        size: '45 MB',
      },
    },
  },

  debian_preseed: {
    id: 'debian_preseed',
    displayName: 'Debian Preseed',
    description: 'Automated Debian installation using preseed configuration',
    icon: '🤖',
    category: 'linux',

    generated: {
      entry_type: 'boot',
      boot_mode: 'preseed',
      requires_internet: true,
      requires_iso: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: `ip=dhcp auto=true priority=critical url=http://\${server_ip}:\${port}/preseed.cfg interface=auto`,
    }),

    assetDiscovery: {
      pattern: 'debian-*/linux',
      requiredFiles: ['linux', 'initrd.gz'],
      versionExtractor: /debian-(\d+)/,
    },

    help: `
      Debian Preseed performs an automated Debian installation.

      Requirements:
      - Debian installer kernel and initrd
      - A preseed.cfg file served by the backend over HTTP

      This is the automated equivalent of Debian netboot installer mode.
    `,
  },

  debian_live: {
    id: 'debian_live',
    displayName: 'Debian Live',
    description: 'Debian live-boot via ISO or squashfs fetch',
    icon: '🐧',
    category: 'linux',

    generated: {
      entry_type: 'boot',
      boot_mode: 'live',
      requires_internet: false,
      requires_iso: true,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent', 'entry_type', 'boot_mode'],
    },

    assetDiscovery: {
      pattern: 'debian-*/*.iso',
      requiredFiles: ['live/vmlinuz', 'live/initrd.img'],
      versionExtractor: /debian-(\d+)/,
    },

    help: `
      Debian Live uses the live-boot fetch-based HTTP path.
      Supports both a full live ISO or live/filesystem.squashfs as the source.
    `,
  },

  // ========== RESCUE & TOOLS ==========

  systemrescue: {
    id: 'systemrescue',
    displayName: 'SystemRescue',
    description: 'System recovery and maintenance tools',
    icon: '🛠️',
    category: 'rescue',

    generated: {
      entry_type: 'boot',
      boot_mode: 'rescue',
      requires_iso: true,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: `ip=dhcp archisobasedir=sysresccd`,
    }),

    assetDiscovery: {
      pattern: 'systemrescue-*/*.iso',
      requiredFiles: ['vmlinuz', 'initrd', '*.iso'],
    },

    downloadUrls: {
      'latest': {
        name: 'SystemRescue Latest',
        iso: 'https://sourceforge.net/projects/systemrescuecd/files/latest/download',
        extractFiles: {
          kernel: 'sysresccd/boot/x86_64/vmlinuz',
          initrd: 'sysresccd/boot/x86_64/sysresccd.img',
        },
        size: '800 MB',
      },
    },

    help: `
      SystemRescue is a bootable system for administrative and recovery tasks.

      Includes tools for:
      - Disk partitioning (GParted, fdisk)
      - Data recovery
      - System repair
      - Password reset
    `,
  },

  kaspersky: {
    id: 'kaspersky',
    displayName: 'Kaspersky Rescue Disk',
    description: 'Antivirus and malware removal tool',
    icon: '🛡️',
    category: 'rescue',

    generated: {
      entry_type: 'boot',
      boot_mode: 'rescue',
      requires_iso: true,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: `dostartx netboot=http://\${server_ip}:\${port}/kaspersky/`,
    }),

    assetDiscovery: {
      pattern: 'kaspersky-*/k-x86_64',
      requiredFiles: ['k-x86_64', 'initrd.xz', '*.iso'],
    },

    downloadUrls: {
      '24': {
        name: 'Kaspersky Rescue Disk 24 (Recommended)',
        iso: 'https://rescuedisk.s.kaspersky-labs.com/updatable/2024/krd.iso',
        extractFiles: {
          kernel: 'krd/boot/grub/k-x86_64',
          initrd: 'krd/boot/grub/initrd.xz',
        },
        size: '~800 MB',
        notes: 'Better UEFI support, requires 2.5GB+ RAM',
      },
      '18': {
        name: 'Kaspersky Rescue Disk 18',
        iso: 'https://rescuedisk.s.kaspersky-labs.com/krd.iso',
        extractFiles: {
          kernel: 'krd/boot/grub/k-x86_64',
          initrd: 'krd/boot/grub/initrd.xz',
        },
        size: '~670 MB',
        notes: 'UEFI Secure Boot NOT supported - must be disabled',
      },
    },

    help: `
      Kaspersky Rescue Disk is a free bootable environment for malware removal.

      Version recommendations:
      - Version 24: Better UEFI support (recommended)
      - Version 18: UEFI Secure Boot must be disabled in BIOS

      Requirements:
      - ISO file extracted to server
      - Kernel (k-x86_64) and initrd (initrd.xz)
      - All ISO contents available via HTTP
      - Minimum 2.5GB RAM for network boot
      - Wired Ethernet connection (WiFi not supported)

      Boot process:
      1. Boots kernel with initrd
      2. Downloads full system from HTTP server
      3. Runs antivirus scan in isolated environment
    `,
  },

  hiren: {
    id: 'hiren',
    displayName: "Hiren's BootCD PE",
    description: 'Windows-based recovery toolkit (WinPE or Legacy ISO)',
    icon: '🧰',
    category: 'rescue',

    // Keep wizard asset discovery enabled for manual ISO scenarios.
    // Actual matching/filtering is handled in AddEntryWizard.
    assetDiscovery: {
      type: 'manual_iso',
    },

    generated: {
      entry_type: 'boot',
      boot_mode: 'rescue',
      requires_iso: true,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: 'ip=dhcp',
    }),

    help: `
      Hiren's BootCD PE supports two explicit boot modes:
      - WinPE via wimboot (preferred)
      - Legacy ISO via memdisk (BIOS)

      Typical flow:
      - Upload ISO in Assets
      - For WinPE mode, extract PE files near ISO (wimboot + sources/boot.wim)
      - For legacy mode, keep ISO and choose Legacy ISO (memdisk)

      Note: file layout differs by image build.
    `,
  },

  gparted: {
    id: 'gparted',
    displayName: 'GParted Live',
    description: 'Partition editor and disk maintenance (official PXE or ISO)',
    icon: '🧩',
    category: 'rescue',

    assetDiscovery: {
      type: 'manual_iso',
    },

    generated: {
      entry_type: 'boot',
      boot_mode: 'rescue',
      requires_iso: true,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: 'iso raw',
    }),

    help: `
      GParted supports official PXE flow and ISO fallback.

      Recommended flow:
      - Upload latest stable GParted ISO in Assets
      - Extract ISO contents near the ISO to expose:
        live/vmlinuz, live/initrd.img, live/filesystem.squashfs
      - Wizard will auto-offer "PXE (official fetch)" when files are detected
      - If files are not extracted, use ISO (legacy memdisk) fallback

      Official docs:
      - https://gparted.org/livepxe.php
      - https://gparted.org/download.php
    `,
  },

  clonezilla: {
    id: 'clonezilla',
    displayName: 'Clonezilla Live',
    description: 'Disk imaging and cloning toolkit (manual ISO)',
    icon: '🧪',
    category: 'rescue',

    assetDiscovery: {
      type: 'manual_iso',
    },

    generated: {
      entry_type: 'boot',
      boot_mode: 'rescue',
      requires_iso: true,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel', 'initrd'],
      optional: ['cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      cmdline: 'iso raw',
    }),

    help: `
      Clonezilla Live is added from manually uploaded ISO assets.

      Recommended flow:
      - Upload latest stable Clonezilla ISO in Assets
      - Create entry from this scenario
      - Boot via ISO (legacy memdisk) or adjust paths manually if needed

      Official docs:
      - https://clonezilla.org/livepxe.php
      - https://clonezilla.org/downloads.php
    `,
  },

  memtest: {
    id: 'memtest',
    displayName: 'Memtest86+',
    description: 'Memory testing utility',
    icon: '🧪',
    category: 'rescue',

    generated: {
      entry_type: 'boot',
      boot_mode: 'tool',
      requires_iso: false,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel'],
      optional: ['description'],
      forbidden: ['initrd', 'cmdline'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      kernel: 'memtest86+/memtest.bin',
    }),

    downloadUrls: {
      'latest': {
        name: 'Memtest86+ v6.20',
        url: 'https://memtest.org/download/v6.20/mt86plus_6.20.64.grub.iso',
        size: '1 MB',
      },
    },
  },

  // ========== WINDOWS ==========

  windows_pe: {
    id: 'windows_pe',
    displayName: 'Windows PE (wimboot)',
    description: 'Windows Preinstallation Environment via wimboot',
    icon: '🪟',
    category: 'windows',

    generated: {
      entry_type: 'boot',
      boot_mode: 'custom',
      requires_iso: true,
      requires_internet: false,
    },

    fields: {
      required: ['name', 'title', 'kernel'],
      optional: ['initrd', 'cmdline', 'description'],
      hidden: ['url', 'parent'],
    },

    template: () => ({
      kernel: 'wimboot',
      initrd: 'winpe/Boot/BCD winpe/Boot/boot.sdi winpe/sources/boot.wim',
      cmdline: '',
    }),

    help: `
      Boots Windows PE using wimboot over HTTP. Generates:
        kernel http://server/wimboot
        initrd http://server/winpe/Boot/BCD       BCD
        initrd http://server/winpe/Boot/boot.sdi  boot.sdi
        initrd http://server/winpe/sources/boot.wim  boot.wim

      Required files on server:
      - /srv/http/wimboot          — download via Assets → Windows tab
      - /srv/http/winpe/Boot/BCD
      - /srv/http/winpe/Boot/boot.sdi
      - /srv/http/winpe/sources/boot.wim

      Extract from Windows ADK (free from Microsoft) or a Windows ISO.
      For Windows 11: add WinPE-WMI and WinPE-SecureStartup packages to the image.

      Adjust the initrd paths if your files are in a different subfolder.
    `,
  },

  // ========== ORGANIZATION ==========

  submenu: {
    id: 'submenu',
    displayName: 'Submenu',
    description: 'Group other menu entries',
    icon: '📂',
    category: 'organization',

    generated: {
      entry_type: 'submenu',
      boot_mode: null,
    },

    fields: {
      required: ['name', 'title'],
      optional: ['description'],
      forbidden: ['kernel', 'initrd', 'cmdline', 'url', 'requires_iso', 'requires_internet'],
      hidden: ['parent'],
    },

    help: `
      A submenu groups related boot entries together.

      Other entries can be placed inside a submenu by setting their parent.
    `,
  },

  separator: {
    id: 'separator',
    displayName: 'Separator',
    description: 'Visual separator line',
    icon: '—',
    category: 'organization',

    generated: {
      entry_type: 'separator',
      boot_mode: null,
    },

    fields: {
      required: ['title'],
      optional: [],
      forbidden: ['kernel', 'initrd', 'cmdline', 'url', 'parent', 'requires_iso', 'requires_internet'],
      readonly: ['name'],
    },

    template: () => ({
      name: `separator_${Date.now()}`,
      title: '---',
    }),
  },

  // ========== ACTIONS ==========

  reboot: {
    id: 'reboot',
    displayName: 'Reboot',
    description: 'Restart the computer',
    icon: '🔄',
    category: 'action',

    generated: {
      entry_type: 'action',
      boot_mode: 'custom',
    },

    fields: {
      required: ['title'],
      optional: [],
      forbidden: ['kernel', 'initrd', 'url'],
      readonly: ['name', 'cmdline'],
    },

    template: () => ({
      name: 'reboot',
      title: 'Reboot Computer',
      cmdline: 'reboot',
    }),
  },

  shell: {
    id: 'shell',
    displayName: 'iPXE Shell',
    description: 'Drop to iPXE command shell',
    icon: '⚙️',
    category: 'action',

    generated: {
      entry_type: 'action',
      boot_mode: 'custom',
    },

    fields: {
      required: ['title'],
      optional: [],
      forbidden: ['kernel', 'initrd', 'url'],
      readonly: ['name', 'cmdline'],
    },

    template: () => ({
      name: 'shell',
      title: 'iPXE Shell',
      cmdline: 'shell',
    }),
  },

  exit_bios: {
    id: 'exit_bios',
    displayName: 'Exit to BIOS',
    description: 'Return to system BIOS/UEFI',
    icon: '🚪',
    category: 'action',

    generated: {
      entry_type: 'action',
      boot_mode: 'custom',
    },

    fields: {
      required: ['title'],
      optional: [],
      forbidden: ['kernel', 'initrd', 'url'],
      readonly: ['name', 'cmdline'],
    },

    template: () => ({
      name: 'exit',
      title: 'Exit to BIOS',
      cmdline: 'exit',
    }),
  },

  // ========== ADVANCED ==========

  chain: {
    id: 'chain',
    displayName: 'Chain to Another Bootloader',
    description: 'Transfer control to another PXE/bootloader',
    icon: '🔗',
    category: 'advanced',

    generated: {
      entry_type: 'chain',
      boot_mode: 'custom',
    },

    fields: {
      required: ['name', 'title', 'url'],
      optional: ['description'],
      forbidden: ['kernel', 'initrd'],
      hidden: ['parent'],
    },

    template: () => ({
      url: 'tftp://${server_ip}/pxelinux.0',
    }),

    help: `
      Chain allows you to transfer control to another bootloader.

      Common uses:
      - Legacy PXE servers (pxelinux.0)
      - GRUB network boot
      - Custom bootloaders

      URL formats:
      - tftp://server/file
      - http://server/file
      - nfs://server/path
    `,
  },

  custom: {
    id: 'custom',
    displayName: 'Custom Entry',
    description: 'Fully manual configuration',
    icon: '🔧',
    category: 'advanced',

    generated: {
      entry_type: 'boot',
      boot_mode: 'custom',
    },

    fields: {
      required: ['name', 'title'],
      optional: ['kernel', 'initrd', 'cmdline', 'url', 'description', 'requires_iso', 'requires_internet'],
      hidden: ['parent'],
    },

    help: `
      Custom entry with no restrictions.

      Use this for advanced scenarios not covered by other templates.
    `,
  },
}

// Category definitions for UI grouping
export const CATEGORIES = {
  linux: {
    name: 'Linux',
    icon: '🐧',
    color: '#E95420',
    description: 'Linux distributions',
  },
  windows: {
    name: 'Windows',
    icon: '🪟',
    color: '#0078D4',
    description: 'Windows systems',
  },
  rescue: {
    name: 'Rescue & Tools',
    icon: '🛠️',
    color: '#10B981',
    description: 'System recovery and diagnostic tools',
  },
  organization: {
    name: 'Menu Organization',
    icon: '📂',
    color: '#6B7280',
    description: 'Structure your menu',
  },
  action: {
    name: 'Actions',
    icon: '⚙️',
    color: '#8B5CF6',
    description: 'System actions',
  },
  advanced: {
    name: 'Advanced',
    icon: '🔧',
    color: '#F59E0B',
    description: 'Advanced configurations',
  },
}

// Helper: Get scenarios by category
export const getScenariosByCategory = (category) => {
  return Object.values(SCENARIOS).filter(s => s.category === category)
}

// Helper: Get scenario by ID
export const getScenario = (id) => {
  return SCENARIOS[id] || null
}

// Substitute ${server_ip}, ${port}, ${version} placeholders in template string values.
const interpolateTemplate = (obj, ctx) => {
  if (!obj || typeof obj !== 'object') return obj
  const result = {}
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'string') {
      result[key] = value
        .replace(/\$\{server_ip\}/g, ctx.server_ip || 'SERVER')
        .replace(/\$\{port\}/g, String(ctx.port || 9021))
        .replace(/\$\{version\}/g, ctx.version || '')
    } else {
      result[key] = value
    }
  }
  return result
}

// Helper: Create entry from scenario
export const createEntryFromScenario = (scenarioId, overrides = {}) => {
  const scenario = SCENARIOS[scenarioId]
  if (!scenario) return null

  const rawTemplate = typeof scenario.template === 'function'
    ? scenario.template(overrides)
    : scenario.template || {}

  const ctx = {
    server_ip: overrides.server_ip || '',
    port: overrides.http_port || 9021,
    version: overrides.version || '',
  }
  const template = interpolateTemplate(rawTemplate, ctx)

  // Strip interpolation-only fields that must not end up in the saved entry
  const { server_ip, http_port, version, ...entryOverrides } = overrides

  return {
    name: entryOverrides.name || `${scenarioId}_${Date.now()}`,
    title: entryOverrides.title || scenario.displayName,
    description: entryOverrides.description || '',
    enabled: true,
    order: entryOverrides.order || 0,
    parent: entryOverrides.parent || null,
    ...scenario.generated,
    ...template,
    ...entryOverrides,
  }
}

export default SCENARIOS
