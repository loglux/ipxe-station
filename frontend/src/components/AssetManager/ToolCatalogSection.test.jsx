import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ToolCatalogSection from './ToolCatalogSection'

const TOOLS = [
  {
    id: 'rescuezilla',
    name: 'Rescuezilla',
    icon: '💾',
    description: 'Disk backup and restore.',
    homepage: 'https://example.org/rz',
    catalog_key: 'rescuezilla',
    warning: '',
    versions: [
      {
        version: '2.6.2',
        name: 'Rescuezilla 2.6.2 (Ubuntu 24.04 LTS)',
        iso_url: 'https://example.org/rz.iso',
        iso_name: 'rescuezilla-2.6.2-64bit.noble.iso',
        dest_folder: 'rescuezilla-2.6.2',
        size_est: '~1.6 GB',
        checksum: `sha256:${'a'.repeat(64)}`,
        recommended: true,
        notes: 'NFS mode reads on demand.',
      },
    ],
  },
  {
    id: 'shredos',
    name: 'ShredOS',
    icon: '🧨',
    description: 'Secure disk erasure.',
    homepage: 'https://example.org/shred',
    catalog_key: 'shredos',
    warning: 'ShredOS erases disks. Boot it only on machines whose data you no longer need.',
    versions: [
      {
        version: '0.42',
        name: 'ShredOS 0.42',
        iso_url: 'https://example.org/full.iso',
        iso_name: 'shredos-full.iso',
        dest_folder: 'shredos-0.42',
        size_est: '~361 MB',
        checksum: `sha1:${'c'.repeat(40)}`,
        recommended: true,
      },
      {
        version: '0.42-lite',
        name: 'ShredOS 0.42 Lite',
        iso_url: 'https://example.org/lite.iso',
        iso_name: 'shredos-lite.iso',
        dest_folder: 'shredos-0.42-lite',
        size_est: '~108 MB',
        recommended: false,
      },
    ],
  },
]

function mockServer({ downloadOk = true, downloadDetail = '' } = {}) {
  const calls = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, init })
    if (url === '/api/assets/tools') return { ok: true, status: 200, json: async () => ({ tools: TOOLS }) }
    if (url === '/api/assets/download/progress') return { ok: true, status: 200, json: async () => ({ downloads: {} }) }
    if (url === '/api/assets/download') {
      return {
        ok: downloadOk,
        status: downloadOk ? 200 : 500,
        json: async () => (downloadOk ? { saved: 'x' } : { detail: downloadDetail }),
      }
    }
    throw new Error(`Unexpected fetch: ${url}`)
  })
  return calls
}

describe('ToolCatalogSection', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('lists the tools with their versions and how each download is verified', async () => {
    mockServer()
    render(<ToolCatalogSection />)

    expect(await screen.findByText(/Rescuezilla$/)).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Rescuezilla 2.6.2 (Ubuntu 24.04 LTS) (~1.6 GB)' })).toBeInTheDocument()
    expect(screen.getByText(/Verified with SHA-256/)).toBeInTheDocument()
    expect(screen.getByText(/Verified with SHA-1/)).toBeInTheDocument()
  })

  it('warns that ShredOS erases disks', async () => {
    mockServer()
    render(<ToolCatalogSection />)

    expect(await screen.findByRole('note')).toHaveTextContent('ShredOS erases disks')
  })

  it('marks a version that is already on disk and offers to download it again', async () => {
    mockServer()
    render(<ToolCatalogSection catalog={{ rescuezilla: [{ version: '2.6.2' }], shredos: [] }} />)

    expect(await screen.findByText('✓ on disk')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '⬇️ Download again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '⬇️ Download ISO' })).toBeInTheDocument()
  })

  it('downloads into the version folder with the checksum and refreshes the catalog', async () => {
    const calls = mockServer()
    const onDownloaded = vi.fn()
    render(<ToolCatalogSection onDownloaded={onDownloaded} />)
    await screen.findByText(/Rescuezilla$/)

    fireEvent.click(screen.getAllByRole('button', { name: '⬇️ Download ISO' })[0])

    expect(await screen.findByText('Downloaded and verified.')).toBeInTheDocument()
    const post = calls.find((c) => c.url === '/api/assets/download')
    expect(JSON.parse(post.init.body)).toEqual({
      url: 'https://example.org/rz.iso',
      dest: 'rescuezilla-2.6.2/rescuezilla-2.6.2-64bit.noble.iso',
      checksum: `sha256:${'a'.repeat(64)}`,
    })
    expect(onDownloaded).toHaveBeenCalled()
  })

  it('shows the server message when a download fails, for example a checksum mismatch', async () => {
    mockServer({ downloadOk: false, downloadDetail: 'Download failed: Checksum mismatch' })
    render(<ToolCatalogSection />)
    await screen.findByText(/Rescuezilla$/)

    fireEvent.click(screen.getAllByRole('button', { name: '⬇️ Download ISO' })[0])

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Checksum mismatch'))
  })

  it('reports a failure to load the list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    render(<ToolCatalogSection />)

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not load the tool list'))
  })
})
