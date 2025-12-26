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
    template: (vars = {}) => ({
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
        name: 'Ubuntu 24.04.1 LTS',
        iso: 'https://releases.ubuntu.com/24.04/ubuntu-24.04.1-live-server-amd64.iso',
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

    template: (vars = {}) => ({
      cmdline: `boot=casper iso-scan/filename=/ubuntu-\${version}.iso quiet splash`,
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
        name: 'Ubuntu 24.04.1 LTS Desktop',
        iso: 'https://releases.ubuntu.com/24.04/ubuntu-24.04.1-desktop-amd64.iso',
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

    template: (vars = {}) => ({
      cmdline: `auto=true priority=critical url=http://\${server_ip}:\${port}/preseed.cfg`,
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

    template: (vars = {}) => ({
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

    template: (vars = {}) => ({
      cmdline: `archisobasedir=sysresccd checksum`,
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
    displayName: 'Windows PE (WIMBoot)',
    description: 'Windows Preinstallation Environment',
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
      initrd: 'bootmgr BCD boot.sdi boot.wim',
      cmdline: '',
    }),

    help: `
      Windows PE requires specific files extracted from a Windows ISO:

      Required files (place in /srv/http/winpe/):
      - wimboot (iPXE WIM bootloader)
      - bootmgr (Windows Boot Manager)
      - Boot/BCD (Boot Configuration Data)
      - Boot/boot.sdi (Service Descriptor Installer)
      - sources/boot.wim (Windows PE image)

      Note: You need a valid Windows license to use WinPE.
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

// Helper: Create entry from scenario
export const createEntryFromScenario = (scenarioId, overrides = {}) => {
  const scenario = SCENARIOS[scenarioId]
  if (!scenario) return null

  const template = typeof scenario.template === 'function'
    ? scenario.template(overrides)
    : scenario.template || {}

  return {
    name: overrides.name || `${scenarioId}_${Date.now()}`,
    title: overrides.title || scenario.displayName,
    description: overrides.description || '',
    enabled: true,
    order: overrides.order || 0,
    parent: overrides.parent || null,
    ...scenario.generated,
    ...template,
    ...overrides,
  }
}

export default SCENARIOS
