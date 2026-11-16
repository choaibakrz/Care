/*
 * Who is using the app: a paired room tablet (`/api/room/session`) or a patient signed in
 * on their own phone or laptop (`/api/auth/session`). Neither: back to the sign-in page.
 * Resolves to { mode: 'room', room, device, patient } or { mode: 'account', user }, or to
 * { mode: 'offline' } when the server cannot be reached (the app then says so).
 */
if (!window.location.pathname.endsWith('/login.html')) {
  const ask = (path) => fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  window.spectrumSessionPromise = (async () => {
    try {
      const room = await ask('/api/room/session')
      if (room.ok) return { mode: 'room', ...(await room.json()) }
      const account = await ask('/api/auth/session')
      if (account.ok) return { mode: 'account', ...(await account.json()) }
      if (room.status === 401 || account.status === 401) {
        window.location.replace('./login.html')
        return null
      }
      return { mode: 'offline' }
    } catch {
      return { mode: 'offline' }
    }
  })()
}
