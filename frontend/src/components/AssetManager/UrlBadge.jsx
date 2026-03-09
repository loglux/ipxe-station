export default function UrlBadge({ url, urlStatus }) {
  const st = urlStatus[url]
  if (!st) return null
  if (st.checking) return <span className="url-badge url-badge-checking">🔍 Checking...</span>
  if (st.ok) {
    const gb = st.size ? ` · ${(st.size / 1024 / 1024 / 1024).toFixed(1)} GB` : ''
    return <span className="url-badge url-badge-ok">✅ Available{gb}</span>
  }
  return <span className="url-badge url-badge-error">❌ Not found — URL may be outdated</span>
}
