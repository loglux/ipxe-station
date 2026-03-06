import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AssetManager from './AssetManager'

const mockResponses = {
  '/api/settings': { poll_interval: 2000 },
  '/api/assets': { http: [], tftp: [], ipxe: [] },
  '/api/assets/catalog': { ubuntu: [], debian: [], windows: [], rescue: [], kaspersky: [] },
  '/api/assets/versions/debian': { products: [] },
  '/api/assets/versions/systemrescue': { versions: [] },
  '/api/assets/versions/kaspersky': { versions: [] },
  '/api/assets/versions/ubuntu': { versions: [] },
  '/api/assets/versions/ubuntu/desktop': { versions: [] },
  '/api/assets/nfs-status': { running: false, exports: [] },
  '/api/assets/download/progress': { downloads: {} },
}

function normalizeUrl(url) {
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return new URL(url).pathname
  }
  return url
}

describe('AssetManager smoke', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const key = normalizeUrl(String(input))
      if (!(key in mockResponses)) {
        throw new Error(`Unexpected fetch call in smoke test: ${key}`)
      }
      return {
        ok: true,
        async json() {
          return mockResponses[key]
        },
      }
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders assets tab without runtime crash', async () => {
    render(<AssetManager />)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Asset Manager' })).toBeInTheDocument()
    })
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
  })
})
