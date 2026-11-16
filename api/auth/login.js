const {
  json,
  normalizeFirstName,
  publicUser,
  responseJson,
  sameOrigin,
  setSessionCookies,
  supabaseFetch,
  updateFirstName
} = require('../_supabase')

function normalizeIdentifier(value) {
  const identifier = String(value || '').trim()
  if (identifier.includes('@')) return { email: identifier.toLowerCase() }
  return { phone: identifier.replace(/[\s().-]/g, '') }
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })

  const identifier = normalizeIdentifier(req.body?.identifier)
  const password = String(req.body?.password || '')
  const firstName = normalizeFirstName(req.body?.first_name)
  if ((!identifier.email && !/^\+?[1-9]\d{7,14}$/.test(identifier.phone)) || password.length < 8 || !firstName) {
    return json(res, 422, { error: 'invalid_input', message: 'Enter a valid first name, contact method and password.' })
  }

  try {
    const response = await supabaseFetch('/auth/v1/token?grant_type=password', {
      method: 'POST',
      body: JSON.stringify({ ...identifier, password })
    })
    const payload = await responseJson(response)
    if (!response.ok || !payload?.access_token || !payload?.refresh_token) {
      return json(res, 401, { error: 'invalid_credentials', message: 'The sign-in details are not valid.' })
    }
    const profileResponse = await updateFirstName(payload.access_token, firstName)
    if (profileResponse.ok) payload.user = await responseJson(profileResponse)
    setSessionCookies(req, res, payload)
    return json(res, 200, { user: publicUser(payload.user) })
  } catch (error) {
    console.error('Patient login failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'Sign-in is temporarily unavailable.' })
  }
}
