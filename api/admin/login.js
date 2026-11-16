const { json, responseJson, sameOrigin, supabaseFetch } = require('../_supabase')

function allowlisted(email) {
  return String(process.env.SPECTRUM_ADMIN_EMAILS || '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .includes(String(email || '').toLowerCase())
}

async function loginWithAccessToken(accessToken) {
  if (!accessToken || accessToken.length > 8192) return { status: 401, body: { error: 'invalid_session', message: 'This sign-in link is invalid or expired.' } }
  const response = await supabaseFetch('/auth/v1/user', {
    headers: { Authorization: `Bearer ${accessToken}` }
  })
  const user = await responseJson(response)
  if (!response.ok || !user?.id) return { status: 401, body: { error: 'invalid_session', message: 'This sign-in link is invalid or expired.' } }
  const isAdmin = user.app_metadata?.role === 'admin' || allowlisted(user.email)
  if (!isAdmin) return { status: 403, body: { error: 'admin_required', message: 'This account is not an administrator account.' } }
  return { status: 200, body: { token: accessToken, operator: user.email || 'administrator', role: 'admin' } }
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const accessToken = String(req.body?.access_token || '').trim()
  if (accessToken) {
    try {
      const result = await loginWithAccessToken(accessToken)
      return json(res, result.status, result.body)
    } catch (error) {
      console.error('Admin magic-link login failed:', error.message)
      return json(res, 503, { error: 'auth_unavailable', message: 'Administrator sign-in is temporarily unavailable.' })
    }
  }
  const email = String(req.body?.email || req.body?.username || '').trim().toLowerCase()
  const password = String(req.body?.password || '')
  if (!email.includes('@') || password.length < 8) return json(res, 422, { error: 'invalid_input', message: 'Enter the administrator email and password.' })

  try {
    const response = await supabaseFetch('/auth/v1/token?grant_type=password', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    })
    const payload = await responseJson(response)
    const user = payload?.user
    const isAdmin = user?.app_metadata?.role === 'admin' || allowlisted(user?.email)
    if (!response.ok || !payload?.access_token || !isAdmin) {
      return json(res, 403, { error: 'admin_required', message: 'This account is not an administrator account.' })
    }
    return json(res, 200, { token: payload.access_token, operator: user.email || email, role: 'admin' })
  } catch (error) {
    console.error('Admin login failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'Administrator sign-in is temporarily unavailable.' })
  }
}
