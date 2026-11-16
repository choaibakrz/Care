const { json } = require('../_supabase')
const { publicRoomSession, requireRoomSession } = require('../_room')

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') return json(res, 405, { error: 'method_not_allowed' })
  const session = await requireRoomSession(req, res)
  if (!session) return
  return json(res, 200, publicRoomSession(session))
}
