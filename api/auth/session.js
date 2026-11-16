const {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  clearSessionCookies,
  json,
  parseCookies,
  publicUser,
  responseJson,
  setSessionCookies,
  supabaseFetch
} = require('../_supabase')

async function currentUser(accessToken) {
  const response = await supabaseFetch('/auth/v1/user', {
    headers: { Authorization: `Bearer ${accessToken}` }
  })
  return { response, payload: await responseJson(response) }
}

async function refreshSession(refreshToken) {
  const response = await supabaseFetch('/auth/v1/token?grant_type=refresh_token', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken })
  })
  return { response, payload: await responseJson(response) }
}

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') return json(res, 405, { error: 'method_not_allowed' })
  const cookies = parseCookies(req)
  if (!cookies[ACCESS_COOKIE]) return json(res, 401, { error: 'not_authenticated' })

  try {
    let result = await currentUser(cookies[ACCESS_COOKIE])
    if (!result.response.ok && cookies[REFRESH_COOKIE]) {
      const refreshed = await refreshSession(cookies[REFRESH_COOKIE])
      if (refreshed.response.ok && refreshed.payload?.access_token) {
        setSessionCookies(req, res, refreshed.payload)
        result = await currentUser(refreshed.payload.access_token)
      }
    }
    if (!result.response.ok || !result.payload?.id) {
      clearSessionCookies(req, res)
      return json(res, 401, { error: 'not_authenticated' })
    }
    return json(res, 200, { user: publicUser(result.payload) })
  } catch (error) {
    console.error('Patient session check failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'Session verification is temporarily unavailable.' })
  }
}
