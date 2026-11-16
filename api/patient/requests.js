const {
  dataPayload,
  json,
  patientDataFetchFor,
  providerMessage,
  publicRequest,
  requestDate,
  requirePatient,
  sameOrigin
} = require('./_patient')

const KINDS = new Set(['water', 'blanket', 'wheelchair', 'pain', 'interpreter', 'care-team'])

module.exports = async function handler(req, res) {
  if (!['GET', 'POST'].includes(req.method)) return json(res, 405, { error: 'method_not_allowed' })
  if (req.method === 'POST' && !sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const patient = await requirePatient(req, res)
  if (!patient) return

  try {
    if (req.method === 'GET') {
      const date = requestDate(req)
      const result = await dataPayload(patientDataFetchFor(patient, `patient_requests?select=id,kind,status,created_at,updated_at&service_date=eq.${date}&order=created_at.desc`))
      if (!result.response.ok) return json(res, 503, { error: 'patient_data_unavailable', message: 'Your requests are temporarily unavailable.' })
      return json(res, 200, { date, items: Array.isArray(result.payload) ? result.payload.map(publicRequest) : [] })
    }

    const kind = String(req.body?.kind || '')
    if (!KINDS.has(kind)) return json(res, 422, { error: 'invalid_request_kind', message: 'Choose a valid request.' })
    const date = requestDate(req)
    const priority = kind === 'pain' ? 'high' : 'normal'
    const result = await dataPayload(patientDataFetchFor(patient, 'patient_requests', {
      method: 'POST',
      headers: { Prefer: 'return=representation' },
      body: JSON.stringify({ patient_id: patient.user.id, service_date: date, kind, priority })
    }))
    if (!result.response.ok || !Array.isArray(result.payload) || !result.payload[0]) {
      return json(res, 400, { error: 'request_not_saved', message: providerMessage(result.payload, 'Your request could not be sent.') })
    }
    return json(res, 201, publicRequest(result.payload[0]))
  } catch (error) {
    console.error('Patient request failed:', error.message)
    return json(res, 503, { error: 'patient_data_unavailable', message: 'Your request is temporarily unavailable.' })
  }
}
