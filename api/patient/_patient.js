const {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  clearSessionCookies,
  json,
  parseCookies,
  responseJson,
  ROOM_DEVICE_COOKIE,
  setSessionCookies,
  supabaseFetch
} = require('../_supabase')
const { requireRoomSession, adminFetch } = require('../_room')

async function authUser(accessToken) {
  const response = await supabaseFetch('/auth/v1/user', {
    headers: { Authorization: `Bearer ${accessToken}` }
  })
  return { response, payload: await responseJson(response) }
}

async function refreshSession(refreshToken) {
  const response = await supabaseFetch('/auth/v1/token?grant_type=refresh_token', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken })
  })
  return { response, payload: await responseJson(response) }
}

/**
 * Resolve the HttpOnly session for a patient route and refresh it when needed.
 * Returns null after writing the final HTTP response, so route handlers can
 * return immediately without ever handling an unverified user id.
 */
async function requirePatient(req, res) {
  const cookies = parseCookies(req)
  if (cookies[ROOM_DEVICE_COOKIE]) {
    const roomSession = await requireRoomSession(req, res)
    if (!roomSession) return null
    if (!roomSession.patient?.id) {
      json(res, 409, { error: 'no_patient_in_room', message: 'No patient is assigned to this room yet.' })
      return null
    }
    return {
      mode: 'room',
      accessToken: null,
      user: { id: roomSession.patient.id, user_metadata: { first_name: roomSession.patient.first_name } },
      room: roomSession.room,
      device: roomSession.device
    }
  }
  if (!cookies[ACCESS_COOKIE]) {
    json(res, 401, { error: 'not_authenticated' })
    return null
  }

  try {
    let accessToken = cookies[ACCESS_COOKIE]
    let result = await authUser(accessToken)
    if (!result.response.ok && cookies[REFRESH_COOKIE]) {
      const refreshed = await refreshSession(cookies[REFRESH_COOKIE])
      if (refreshed.response.ok && refreshed.payload?.access_token) {
        accessToken = refreshed.payload.access_token
        setSessionCookies(req, res, refreshed.payload)
        result = await authUser(accessToken)
      }
    }
    if (!result.response.ok || !result.payload?.id) {
      clearSessionCookies(req, res)
      json(res, 401, { error: 'not_authenticated' })
      return null
    }
    return { accessToken, user: result.payload }
  } catch (error) {
    console.error('Patient authentication failed:', error.message)
    json(res, 503, { error: 'auth_unavailable', message: 'Patient data is temporarily unavailable.' })
    return null
  }
}

function patientDataFetch(accessToken, path, init = {}) {
  return supabaseFetch(`/rest/v1/${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(init.headers || {})
    }
  })
}

function roomDataFetch(path, init = {}) {
  return adminFetch(path, init)
}

function patientDataFetchFor(patient, path, init = {}) {
  if (patient.mode !== 'room') return patientDataFetch(patient.accessToken, path, init)
  const resources = {
    patient_day_items: 'room_patient_day_items',
    patient_questions: 'room_patient_questions',
    patient_requests: 'room_patient_requests',
    patient_mood: 'room_patient_mood'
  }
  const resource = Object.keys(resources).find((key) => path.startsWith(key))
  if (!resource) throw new Error('Unknown room patient resource.')
  const suffix = path.slice(resource.length)
  const nextPath = init.method === 'POST' ? resources[resource] + suffix : `${resources[resource]}${suffix}${suffix.includes('?') ? '&' : '?'}patient_id=eq.${encodeURIComponent(patient.user.id)}`
  return roomDataFetch(nextPath, init)
}

function rpcFetch(accessToken, functionName, body) {
  return patientDataFetch(accessToken, `rpc/${functionName}`, {
    method: 'POST',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify(body)
  })
}

function validDateKey(value) {
  const date = String(value || '')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const parsed = new Date(`${date}T00:00:00.000Z`)
  return parsed.toISOString().slice(0, 10) === date ? date : null
}

function todayKey() {
  return new Date().toISOString().slice(0, 10)
}

function requestDate(req) {
  const url = new URL(req.url || '/', `https://${req.headers.host || 'spectrum.local'}`)
  return validDateKey(url.searchParams.get('date')) || todayKey()
}

async function dataPayload(responsePromise) {
  const response = await responsePromise
  return { response, payload: await responseJson(response) }
}

function providerMessage(payload, fallback) {
  return typeof payload?.message === 'string' ? payload.message : fallback
}

function timeLabel(value) {
  return value ? String(value).slice(0, 5) : null
}

function publicProgramItem(item) {
  return {
    time: timeLabel(item.time),
    kind: item.kind,
    until: timeLabel(item.until_time)
  }
}

function publicQuestion(item) {
  return {
    id: String(item.id),
    text: String(item.text || ''),
    created_at: Date.parse(item.created_at) || Date.now()
  }
}

const STATUS_INDEX = { sent: 0, seen: 1, on_the_way: 2, done: 3 }

function publicRequest(item) {
  return {
    id: String(item.id),
    kind: item.kind,
    status: item.status,
    status_index: STATUS_INDEX[item.status] ?? 0,
    created_at: Date.parse(item.created_at) || Date.now(),
    updated_at: Date.parse(item.updated_at) || Date.now()
  }
}

module.exports = {
  dataPayload,
  json,
  patientDataFetch,
  patientDataFetchFor,
  providerMessage,
  publicProgramItem,
  publicQuestion,
  publicRequest,
  requestDate,
  requirePatient,
  rpcFetch,
  sameOrigin: require('../_supabase').sameOrigin,
  validDateKey
}
