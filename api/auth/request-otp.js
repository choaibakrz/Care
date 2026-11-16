const {
  json,
  responseJson,
  sameOrigin,
  supabaseFetch
} = require('../_supabase')

function normalizePhone(value) {
  return String(value || '').trim().replace(/[\s().-]/g, '')
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })

  const phone = normalizePhone(req.body?.phone)
  if (!/^\+?[1-9]\d{7,14}$/.test(phone)) {
    return json(res, 422, { error: 'invalid_phone', message: 'Enter the phone number in international format.' })
  }

  try {
    const response = await supabaseFetch('/auth/v1/otp', {
      method: 'POST',
      body: JSON.stringify({ phone, create_user: false })
    })
    const payload = await responseJson(response)
    if (!response.ok) {
      console.warn('Patient OTP request rejected:', response.status, payload?.msg || payload?.message || 'unknown error')
    }
    // Keep the response generic so the endpoint does not reveal whether a phone is registered.
    return json(res, 200, { ok: true, message: 'If the number is registered, a code has been sent.' })
  } catch (error) {
    console.error('Patient OTP request failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'SMS sign-in is temporarily unavailable.' })
  }
}
