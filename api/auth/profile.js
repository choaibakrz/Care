const {
  ACCESS_COOKIE,
  json,
  normalizeFirstName,
  parseCookies,
  publicUser,
  responseJson,
  sameOrigin,
  supabaseFetch,
  updateFirstName
} = require('../_supabase')

module.exports = async function handler(req, res) {
  if (req.method !== 'PUT') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })

  const accessToken = parseCookies(req)[ACCESS_COOKIE]
  const firstName = normalizeFirstName(req.body?.first_name)
  if (!accessToken) return json(res, 401, { error: 'not_authenticated' })
  if (!firstName) return json(res, 422, { error: 'invalid_first_name', message: 'Enter a valid first name.' })

  try {
    const response = await updateFirstName(accessToken, firstName)
    const payload = await responseJson(response)
    if (!response.ok || !payload?.id) return json(res, 400, { error: 'profile_update_failed', message: 'Your first name could not be updated.' })
    return json(res, 200, { user: publicUser(payload) })
  } catch (error) {
    console.error('Patient profile update failed:', error.message)
    return json(res, 503, { error: 'auth_unavailable', message: 'Your profile is temporarily unavailable.' })
  }
}
