const {
  ACCESS_COOKIE,
  clearSessionCookies,
  json,
  parseCookies,
  sameOrigin,
  supabaseFetch
} = require('../_supabase')

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const cookies = parseCookies(req)
  try {
    if (cookies[ACCESS_COOKIE]) {
      await supabaseFetch('/auth/v1/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${cookies[ACCESS_COOKIE]}` }
      })
    }
  } catch (error) {
    console.warn('Patient remote logout failed:', error.message)
  }
  clearSessionCookies(req, res)
  return json(res, 200, { ok: true })
}
