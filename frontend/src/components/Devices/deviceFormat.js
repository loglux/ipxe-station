export const DAY_S = 24 * 60 * 60

function makerWord(device) {
  return (device.manufacturer || '').split(/[\s,.]+/)[0].toLowerCase()
}

/**
 * Readable brand and model. HP repeats its brand inside the model name, and Lenovo puts a machine-type
 * code in "product" and the friendly name (ThinkPad T14 Gen 3) in "family".
 */
export function deviceName(device) {
  const maker = device.manufacturer || ''
  const product = device.product || ''
  const word = makerWord(device)
  if (word === 'lenovo' && device.family) return `${maker} ${device.family}`.trim()
  if (word && product.toLowerCase().startsWith(word)) return product
  return [maker, product].filter(Boolean).join(' ') || 'Unknown machine'
}

/** Secondary line: the product number, or Lenovo's machine-type code when it is not in the name. */
export function deviceSub(device) {
  if (makerWord(device) === 'lenovo' && device.family && device.product) {
    return `Type ${device.product}`
  }
  return device.sku ? `SKU ${device.sku}` : ''
}

export function bootMode(device) {
  const platform = { efi: 'UEFI', pcbios: 'BIOS' }[device.platform] || device.platform || ''
  const arch = { x86_64: 'x64', i386: 'x86', arm64: 'ARM64' }[device.arch] || device.arch || ''
  return [platform, arch].filter(Boolean).join(' ')
}

export function formatAge(seconds) {
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < DAY_S) return `${Math.floor(seconds / 3600)} h ago`
  return `${Math.floor(seconds / DAY_S)} d ago`
}
