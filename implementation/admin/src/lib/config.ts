/** Where the panel finds the others. All values come from `.env.local`, never from the user. */
function env(name: string, fallback: string): string {
  const value = (import.meta.env as Record<string, string | undefined>)[name]
  return value && value.trim() ? value.trim().replace(/\/$/, '') : fallback
}

/**
 * HACKATHON: when the console is served by the clinic server (`/admin/`), it talks to the
 * server that served it (its own origin, e.g. http://192.168.1.20:8080), so phones and
 * laptops on the LAN work without a rebuild: an empty VITE_API_URL, or one naming this
 * computer (localhost) while the page was opened from another address, means "this origin".
 * The dev server and `vite preview` (4173) keep VITE_API_URL or http://localhost:8080.
 */
const LOOPBACK = /^(https?|wss?):\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i

function servedByServer(): boolean {
  if (typeof window === 'undefined' || !window.location?.origin?.startsWith('http')) return false
  return !import.meta.env.DEV && window.location.port !== '4173'
}

function resolveApiUrl(): string {
  const configured = env('VITE_API_URL', '')
  // A loopback VITE_API_URL names "the server on this computer": the one that served the page
  // is that server, whatever its port (http://localhost:18090/admin/ talks to :18090).
  if (servedByServer() && (!configured || LOOPBACK.test(configured))) {
    return window.location.origin
  }
  return configured || 'http://localhost:8080'
}

function resolveWsUrl(api: string): string {
  const derived = `${api.replace(/^http/, 'ws')}/ws`
  const configured = env('VITE_WS_URL', '')
  if (!configured || (LOOPBACK.test(configured) && (servedByServer() || !LOOPBACK.test(api)))) return derived
  return configured
}

const apiUrl = resolveApiUrl()

export const config = {
  /** Real mode is the safe default. Set VITE_USE_MOCK=true only for the invented demo clinic. */
  useMock: import.meta.env.VITE_USE_MOCK === 'true',
  apiUrl,
  wsUrl: resolveWsUrl(apiUrl),
  /** The existing jury screen of `b13_ecran`. Linked, not rebuilt. */
  juryUrl: env('VITE_JURY_URL', 'http://localhost:8000/jury'),
  /** The robot-side screen. Its `POST /api/arret_urgence` is the documented backup stop. */
  robotScreenUrl: env('VITE_ROBOT_SCREEN_URL', 'http://localhost:8000'),
} as const

export const ESTOP_FALLBACK_PATH = '/api/arret_urgence'
export const STALE_AFTER_MS = 5000
