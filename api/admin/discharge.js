const { json, responseJson } = require('../_supabase')
const { adminFetch, requireAdmin } = require('../_room')

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  const admin = await requireAdmin(req, res)
  if (!admin) return
  const roomId = String(req.body?.room_id || '').trim()
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{1,31}$/.test(roomId)) {
    return json(res, 422, { error: 'invalid_room', message: 'Choose a valid room.' })
  }

  try {
    const activeResponse = await adminFetch(`room_assignments?select=id,patient_id&room_id=eq.${encodeURIComponent(roomId)}&discharged_at=is.null&limit=1`)
    const active = await responseJson(activeResponse)
    const assignment = Array.isArray(active) ? active[0] : null
    if (!activeResponse.ok) return json(res, 503, { error: 'room_unavailable', message: 'The room could not be checked.' })
    if (!assignment) return json(res, 404, { error: 'room_empty', message: 'There is no admitted patient in this room.' })

    const dischargedAt = new Date().toISOString()
    const assignmentResponse = await adminFetch(`room_assignments?id=eq.${encodeURIComponent(assignment.id)}&discharged_at=is.null`, {
      method: 'PATCH',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({ discharged_at: dischargedAt })
    })
    if (!assignmentResponse.ok) return json(res, 503, { error: 'discharge_failed', message: 'The room assignment could not be closed.' })

    const patientResponse = await adminFetch(`room_patients?id=eq.${encodeURIComponent(assignment.patient_id)}&status=eq.admitted`, {
      method: 'PATCH',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({ status: 'discharged', discharged_at: dischargedAt })
    })
    if (!patientResponse.ok) {
      await adminFetch(`room_assignments?id=eq.${encodeURIComponent(assignment.id)}`, {
        method: 'PATCH',
        headers: { Prefer: 'return=minimal' },
        body: JSON.stringify({ discharged_at: null })
      })
      return json(res, 503, { error: 'discharge_failed', message: 'The patient record could not be closed.' })
    }

    const deviceResponse = await adminFetch(`room_devices?room_id=eq.${encodeURIComponent(roomId)}&revoked_at=is.null`, {
      method: 'PATCH',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({ revoked_at: dischargedAt, pairing_code_hash: null, pairing_expires_at: null, session_token_hash: null, session_expires_at: null })
    })
    if (!deviceResponse.ok) {
      console.error('Tablet revocation after discharge failed:', await responseJson(deviceResponse))
      return json(res, 503, { error: 'discharge_failed', message: 'The patient was discharged, but the room tablet could not be reset.' })
    }
    return json(res, 200, { roomId, patientId: assignment.patient_id, dischargedAt, dischargedBy: admin.user.id })
  } catch (error) {
    console.error('Admin discharge failed:', error.message)
    return json(res, 503, { error: 'discharge_unavailable', message: 'The room could not be discharged right now.' })
  }
}
