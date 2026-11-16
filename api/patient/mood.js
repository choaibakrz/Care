const {
  dataPayload,
  json,
  patientDataFetchFor,
  providerMessage,
  requestDate,
  requirePatient,
  sameOrigin
} = require('./_patient')

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const patient = await requirePatient(req, res)
  if (!patient) return

  const value = Number(req.body?.value)
  if (!Number.isInteger(value) || value < 1 || value > 5) return json(res, 422, { error: 'invalid_mood', message: 'Choose a mood from 1 to 5.' })
  try {
    const result = await dataPayload(patientDataFetchFor(patient, 'patient_mood', {
      method: 'POST',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({ patient_id: patient.user.id, service_date: requestDate(req), value })
    }))
    if (!result.response.ok) return json(res, 400, { error: 'mood_not_saved', message: providerMessage(result.payload, 'Your check-in could not be saved.') })
    res.statusCode = 204
    return res.end()
  } catch (error) {
    console.error('Patient mood request failed:', error.message)
    return json(res, 503, { error: 'patient_data_unavailable', message: 'Your check-in is temporarily unavailable.' })
  }
}
