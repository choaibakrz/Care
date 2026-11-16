const {
  json,
  normalizeFirstName,
  publicUser,
  responseJson,
  sameOrigin,
  setSessionCookies,
  supabaseFetch
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
    const response = await supabaseFetch('/auth/v1/signup', {
      method: 'POST',
      body: JSON.stringify({ ...identifier, password, data: { first_name: firstName } })
    })
    const payload = await responseJson(response)
    if (!response.ok) {
      return json(res, 400, { error: 'signup_failed', message: 'This account could not be created. Check the details and try again.' })
    }

    if (payload?.access_token && payload?.refresh_token) {
      setSessionCookies(req, res, payload)
      return json(res, 201, { user: publicUser(payload.user), needsConfirmation: false })
    }

    return json(res, 201, {
      user: publicUser(payload?.user),
      needsConfirmation: true,
      message: identifier.email
        ? 'Account created. Check your email to confirm it, then sign in.'
        : 'Account created. Check your phone for the confirmation code, then sign in.'
    })
  } catch (error) {
    console.error('Patient signup failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'Account creation is temporarily unavailable.' })
  }
}
