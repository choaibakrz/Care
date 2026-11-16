const {
  dataPayload,
  json,
  patientDataFetchFor,
  requirePatient,
  sameOrigin
} = require('../_patient')

function validId(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ''))
}

module.exports = async function handler(req, res) {
  if (req.method !== 'DELETE') return json(res, 405, { error: 'method_not_allowed' })
  if (!sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const patient = await requirePatient(req, res)
  if (!patient) return
  const id = req.query?.id
  if (!validId(id)) return json(res, 422, { error: 'invalid_question_id' })

  try {
    const result = await dataPayload(patientDataFetchFor(patient, `patient_questions?id=eq.${encodeURIComponent(id)}&patient_id=eq.${encodeURIComponent(patient.user.id)}`, {
      method: 'DELETE',
      headers: { Prefer: 'return=representation' }
    }))
    if (!result.response.ok) return json(res, 400, { error: 'question_not_deleted' })
    res.statusCode = 204
    return res.end()
  } catch (error) {
    console.error('Patient question delete failed:', error.message)
    return json(res, 503, { error: 'patient_data_unavailable', message: 'Your question could not be removed.' })
  }
}
