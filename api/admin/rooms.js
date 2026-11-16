const { json, responseJson } = require('../_supabase')
const { adminFetch, normalizeFirstName, normalizeRecordRef, randomPairingCode, requireAdmin, hashToken } = require('../_room')

const CONFIGURED_ROOM_IDS = new Set(['room-212', 'room-213', 'room-216'])

function isConfiguredRoom(roomId) {
  return CONFIGURED_ROOM_IDS.has(roomId)
}

function publicPatient(value) {
  return value ? {
    id: value.id,
    firstName: value.first_name,
    medicalRecordRef: value.medical_record_ref,
    status: value.status,
    admittedAt: value.admitted_at
  } : null
}

function publicDevice(value, pairingCode = null) {
  return value ? {
    id: value.id,
    label: value.device_label,
    roomId: value.room_id,
    online: Boolean(value.last_seen_at && Date.now() - Date.parse(value.last_seen_at) < 120000),
    paired: Boolean(value.session_token_hash && !value.revoked_at),
    pairingCode
  } : null
}

async function listRows(path) {
  const response = await adminFetch(path)
  return { response, payload: await responseJson(response) }
}

async function rooms() {
  const roomResult = await listRows('clinic_rooms?select=id,label,wing,floor&id=in.(room-212,room-213,room-216)&order=floor.asc,label.asc')
  if (!roomResult.response.ok || !Array.isArray(roomResult.payload)) throw new Error('Rooms could not be loaded.')
  const assignmentResult = await listRows('room_assignments?select=id,room_id,patient_id,assigned_at&discharged_at=is.null')
  const patientsResult = await listRows('room_patients?select=id,first_name,medical_record_ref,status,admitted_at&status=eq.admitted')
  const devicesResult = await listRows('room_devices?select=id,device_label,room_id,last_seen_at,session_token_hash,revoked_at&revoked_at=is.null')
  if (!assignmentResult.response.ok || !patientsResult.response.ok || !devicesResult.response.ok) throw new Error('Room occupancy could not be loaded.')
  const assignments = Array.isArray(assignmentResult.payload) ? assignmentResult.payload : []
  const patients = new Map((Array.isArray(patientsResult.payload) ? patientsResult.payload : []).map((patient) => [patient.id, patient]))
  const devices = new Map((Array.isArray(devicesResult.payload) ? devicesResult.payload : []).map((device) => [device.room_id, device]))
  return roomResult.payload.map((room) => {
    const assignment = assignments.find((entry) => entry.room_id === room.id)
    return {
      id: room.id,
      label: room.label,
      wing: room.wing,
      floor: room.floor,
      patient: publicPatient(assignment ? patients.get(assignment.patient_id) : null),
      device: publicDevice(devices.get(room.id) || null)
    }
  })
}

async function admitPatient(req, res, admin) {
  const firstName = normalizeFirstName(req.body?.first_name)
  const medicalRecordRef = normalizeRecordRef(req.body?.medical_record_ref)
  const roomId = String(req.body?.room_id || '').trim()
  if (!firstName || !medicalRecordRef || !isConfiguredRoom(roomId)) {
    return json(res, 422, { error: 'invalid_patient', message: 'Enter a first name, a medical record reference and a valid room.' })
  }

  const roomResult = await listRows(`clinic_rooms?select=id&id=eq.${encodeURIComponent(roomId)}&limit=1`)
  if (!roomResult.response.ok || !roomResult.payload?.[0]) return json(res, 404, { error: 'room_not_found', message: 'This room does not exist.' })

  const existing = await listRows(`room_assignments?select=id&room_id=eq.${encodeURIComponent(roomId)}&discharged_at=is.null&limit=1`)
  if (!existing.response.ok) return json(res, 503, { error: 'room_unavailable', message: 'The room could not be checked.' })
  if (existing.payload?.[0]) return json(res, 409, { error: 'room_occupied', message: 'Discharge the current patient before assigning another patient to this room.' })

  const patientResponse = await adminFetch('room_patients', {
    method: 'POST',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify({ first_name: firstName, medical_record_ref: medicalRecordRef, status: 'admitted', admitted_at: new Date().toISOString(), created_by: admin.user.id })
  })
  const patients = await responseJson(patientResponse)
  const patient = Array.isArray(patients) ? patients[0] : null
  if (!patientResponse.ok || !patient) return json(res, 400, { error: 'patient_not_created', message: 'The patient record could not be created.' })

  const assignmentResponse = await adminFetch('room_assignments', {
    method: 'POST',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify({ room_id: roomId, patient_id: patient.id, assigned_by: admin.user.id })
  })
  const assignments = await responseJson(assignmentResponse)
  if (!assignmentResponse.ok || !Array.isArray(assignments) || !assignments[0]) {
    await adminFetch(`room_patients?id=eq.${encodeURIComponent(patient.id)}`, { method: 'DELETE' })
    if (assignmentResponse.status === 409) return json(res, 409, { error: 'room_occupied', message: 'The room was assigned to another patient. Refresh and try again.' })
    return json(res, 400, { error: 'patient_not_assigned', message: 'The patient was created but could not be assigned to the room.' })
  }
  return json(res, 201, { patient: publicPatient(patient), roomId: roomId })
}

async function createDevice(req, res) {
  const roomId = String(req.body?.room_id || '').trim()
  const label = String(req.body?.label || '').trim() || `Tablet ${roomId}`
  if (!isConfiguredRoom(roomId) || label.length > 60) return json(res, 422, { error: 'invalid_device', message: 'Choose one of the three configured rooms and a valid tablet label.' })
  const roomResult = await listRows(`clinic_rooms?select=id&id=eq.${encodeURIComponent(roomId)}&limit=1`)
  if (!roomResult.response.ok || !roomResult.payload?.[0]) return json(res, 404, { error: 'room_not_found', message: 'This room does not exist.' })
  const existing = await listRows(`room_devices?select=id,room_id,device_label,session_token_hash,last_seen_at,revoked_at&room_id=eq.${encodeURIComponent(roomId)}&revoked_at=is.null&limit=1`)
  if (!existing.response.ok) return json(res, 503, { error: 'device_unavailable', message: 'The tablet registry could not be checked.' })

  const pairingCode = randomPairingCode()
  const existingDevice = existing.payload?.[0]
  if (existingDevice?.session_token_hash) return json(res, 409, { error: 'room_device_exists', message: 'This room already has a paired tablet.' })
  const response = existingDevice
    ? await adminFetch(`room_devices?id=eq.${encodeURIComponent(existingDevice.id)}&revoked_at=is.null`, {
      method: 'PATCH',
      headers: { Prefer: 'return=representation' },
      body: JSON.stringify({ device_label: label, pairing_code_hash: hashToken(pairingCode), pairing_expires_at: new Date(Date.now() + 1000 * 60 * 15).toISOString() })
    })
    : await adminFetch('room_devices', {
      method: 'POST',
      headers: { Prefer: 'return=representation' },
      body: JSON.stringify({ room_id: roomId, device_label: label, pairing_code_hash: hashToken(pairingCode), pairing_expires_at: new Date(Date.now() + 1000 * 60 * 15).toISOString() })
    })
  const devices = await responseJson(response)
  if (!response.ok || !Array.isArray(devices) || !devices[0]) return json(res, response.status === 409 ? 409 : 400, { error: 'device_not_created', message: 'The tablet could not be registered.' })
  return json(res, 201, { device: publicDevice(devices[0], pairingCode), pairingCode })
}

module.exports = async function handler(req, res) {
  if (!['GET', 'POST'].includes(req.method)) return json(res, 405, { error: 'method_not_allowed' })
  const admin = await requireAdmin(req, res)
  if (!admin) return
  try {
    if (req.method === 'GET') return json(res, 200, { rooms: await rooms() })
    return admitPatient(req, res, admin)
  } catch (error) {
    console.error('Admin room operation failed:', error.message)
    return json(res, 503, { error: 'room_operation_unavailable', message: 'The room operation is temporarily unavailable.' })
  }
}

module.exports.createDevice = async function createDeviceHandler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  const admin = await requireAdmin(req, res)
  if (!admin) return
  try { return createDevice(req, res) } catch (error) {
    console.error('Admin device operation failed:', error.message)
    return json(res, 503, { error: 'device_operation_unavailable', message: 'The tablet operation is temporarily unavailable.' })
  }
}
