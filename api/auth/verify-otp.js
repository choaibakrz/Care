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

function normalizePhone(value) {
  return String(value || '').trim().replace(/[\s().-]/g, '')
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })

  const phone = normalizePhone(req.body?.phone)
  const token = String(req.body?.token || '').trim()
  const firstName = normalizeFirstName(req.body?.first_name)
  if (!/^\+?[1-9]\d{7,14}$/.test(phone) || !/^\d{6}$/.test(token) || !firstName) {
    return json(res, 422, { error: 'invalid_code', message: 'Enter your first name and the six-digit SMS code.' })
  }

  try {
    const response = await supabaseFetch('/auth/v1/verify', {
      method: 'POST',
      body: JSON.stringify({ phone, token, type: 'sms' })
    })
    const payload = await responseJson(response)
    if (!response.ok || !payload?.access_token || !payload?.refresh_token) {
      return json(res, 401, { error: 'invalid_code', message: 'That code is invalid or has expired.' })
    }
    const profileResponse = await updateFirstName(payload.access_token, firstName)
    if (profileResponse.ok) payload.user = await responseJson(profileResponse)
    setSessionCookies(req, res, payload)
    return json(res, 200, { user: publicUser(payload.user) })
  } catch (error) {
    console.error('Patient OTP verification failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'SMS sign-in is temporarily unavailable.' })
  }
}
