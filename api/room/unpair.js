const { clearRoomDeviceCookie, json, sameOrigin } = require('../_supabase')

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  clearRoomDeviceCookie(req, res)
  return json(res, 200, { ok: true })
}
