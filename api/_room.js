const crypto = require('node:crypto')
const {
  ROOM_DEVICE_COOKIE,
  json,
  parseCookies,
  responseJson,
  sameOrigin,
  supabaseAdminFetch,
  supabaseFetch,
  setRoomDeviceCookie,
  clearRoomDeviceCookie
} = require('./_supabase')

function bearerToken(req) {
  const value = String(req.headers.authorization || '')
  return value.startsWith('Bearer ') ? value.slice(7).trim() : ''
}

function hashToken(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex')
}

function randomToken(bytes = 32) {
  return crypto.randomBytes(bytes).toString('base64url')
}

function randomPairingCode() {
  return crypto.randomBytes(6).toString('hex').toUpperCase()
}

function normalizeFirstName(value) {
  const firstName = String(value || '').trim().replace(/\s+/g, ' ')
  if (!/^[\p{L}\p{M}][\p{L}\p{M}'’ -]{0,39}$/u.test(firstName)) return null
  return firstName
}

function normalizeRecordRef(value) {
  const reference = String(value || '').trim().replace(/\s+/g, ' ')
  if (!/^[\p{L}\p{N}][\p{L}\p{N}._/ -]{0,63}$/u.test(reference)) return null
  return reference
}

function adminEmails() {
  return String(process.env.SPECTRUM_ADMIN_EMAILS || '')
    .split(',')
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)
}

async function verifyAdmin(req) {
  const accessToken = bearerToken(req)
  if (!accessToken) return null
  const response = await supabaseFetch('/auth/v1/user', { headers: { Authorization: `Bearer ${accessToken}` } })
  const user = await responseJson(response)
  if (!response.ok || !user?.id) return null
  const role = user.app_metadata?.role
  const allowlisted = typeof user.email === 'string' && adminEmails().includes(user.email.toLowerCase())
  if (role !== 'admin' && !allowlisted) return null
  return { accessToken, user }
}

async function requireAdmin(req, res) {
  try {
    const admin = await verifyAdmin(req)
    if (!admin) {
      json(res, 403, { error: 'admin_required', message: 'An administrator session is required.' })
      return null
    }
    return admin
  } catch (error) {
    console.error('Admin authentication failed:', error.message)
    json(res, 503, { error: 'auth_unavailable', message: 'Administrator authentication is temporarily unavailable.' })
    return null
  }
}

function adminFetch(path, init = {}) {
  return supabaseAdminFetch(`/rest/v1/${path}`, init)
}

function rpcAdmin(functionName, body) {
  return supabaseAdminFetch(`/rest/v1/rpc/${functionName}`, {
    method: 'POST',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify(body)
  })
}

async function roomData(device) {
  const roomResponse = await adminFetch(`clinic_rooms?select=id,label,wing,floor&id=eq.${encodeURIComponent(device.room_id)}`)
  const rooms = await responseJson(roomResponse)
  const room = Array.isArray(rooms) ? rooms[0] : null
  if (!roomResponse.ok || !room) return null

  const assignmentResponse = await adminFetch(`room_assignments?select=patient_id,assigned_at&room_id=eq.${encodeURIComponent(device.room_id)}&discharged_at=is.null&limit=1`)
  const assignments = await responseJson(assignmentResponse)
  const assignment = Array.isArray(assignments) ? assignments[0] : null
  let patient = null
  if (assignment?.patient_id) {
    const patientResponse = await adminFetch(`room_patients?select=id,first_name,status&id=eq.${encodeURIComponent(assignment.patient_id)}`)
    const patients = await responseJson(patientResponse)
    patient = Array.isArray(patients) ? patients[0] ?? null : null
  }
  return { room, patient, assignment }
}

async function requireRoomSession(req, res) {
  const token = parseCookies(req)[ROOM_DEVICE_COOKIE]
  if (!token) {
    json(res, 401, { error: 'room_device_not_paired', message: 'This tablet is not paired with a room.' })
    return null
  }

  try {
    const now = new Date().toISOString()
    const response = await adminFetch(`room_devices?select=id,room_id,device_label,session_expires_at,revoked_at&session_token_hash=eq.${encodeURIComponent(hashToken(token))}&revoked_at=is.null&session_expires_at=gt.${encodeURIComponent(now)}&limit=1`)
    const devices = await responseJson(response)
    const device = Array.isArray(devices) ? devices[0] : null
    if (!response.ok || !device) {
      clearRoomDeviceCookie(req, res)
      json(res, 401, { error: 'room_device_session_expired', message: 'This tablet needs to be paired again.' })
      return null
    }
    const data = await roomData(device)
    if (!data) {
      clearRoomDeviceCookie(req, res)
      json(res, 409, { error: 'room_not_configured', message: 'This room is not configured yet.' })
      return null
    }
    void adminFetch(`room_devices?id=eq.${encodeURIComponent(device.id)}`, {
      method: 'PATCH',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({ last_seen_at: new Date().toISOString() })
    }).catch((error) => console.error('Room device heartbeat failed:', error.message))
    return { device, ...data }
  } catch (error) {
    console.error('Room device session failed:', error.message)
    json(res, 503, { error: 'room_access_unavailable', message: 'Room access is temporarily unavailable.' })
    return null
  }
}

function publicRoomSession(session) {
  return {
    device: { id: session.device.id, label: session.device.device_label },
    room: { id: session.room.id, label: session.room.label, wing: session.room.wing, floor: session.room.floor },
    patient: session.patient ? { id: session.patient.id, firstName: session.patient.first_name, status: session.patient.status } : null
  }
}

async function pairRoomDevice(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const code = String(req.body?.code || '').trim().toUpperCase()
  if (!/^[A-Z0-9-]{8,32}$/.test(code)) return json(res, 422, { error: 'invalid_pairing_code', message: 'Enter the pairing code shown by the care team.' })

  try {
    const now = new Date().toISOString()
    const response = await adminFetch(`room_devices?select=id,room_id,device_label&pairing_code_hash=eq.${encodeURIComponent(hashToken(code))}&pairing_expires_at=gt.${encodeURIComponent(now)}&revoked_at=is.null&limit=1`)
    const devices = await responseJson(response)
    const device = Array.isArray(devices) ? devices[0] : null
    if (!response.ok || !device) return json(res, 401, { error: 'invalid_pairing_code', message: 'This pairing code is invalid or has expired.' })

    const sessionToken = randomToken()
    const update = await adminFetch(`room_devices?id=eq.${encodeURIComponent(device.id)}`, {
      method: 'PATCH',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({
        pairing_code_hash: null,
        pairing_expires_at: null,
        session_token_hash: hashToken(sessionToken),
        session_expires_at: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString(),
        last_seen_at: new Date().toISOString()
      })
    })
    if (!update.ok) return json(res, 503, { error: 'pairing_failed', message: 'The tablet could not be paired. Please try again.' })
    setRoomDeviceCookie(req, res, sessionToken)
    const data = await roomData(device)
    if (!data) return json(res, 409, { error: 'room_not_configured', message: 'This room is not configured yet.' })
    return json(res, 200, publicRoomSession({ device, ...data }))
  } catch (error) {
    console.error('Room device pairing failed:', error.message)
    return json(res, 503, { error: 'room_access_unavailable', message: 'Room pairing is temporarily unavailable.' })
  }
}

module.exports = {
  adminFetch,
  hashToken,
  normalizeFirstName,
  normalizeRecordRef,
  pairRoomDevice,
  publicRoomSession,
  randomPairingCode,
  randomToken,
  requireAdmin,
  requireRoomSession,
  responseJson,
  rpcAdmin
}
