const {
  dataPayload,
  json,
  patientDataFetchFor,
  providerMessage,
  publicQuestion,
  requirePatient,
  sameOrigin
} = require('./_patient')

const MAX_QUESTION_LENGTH = 300

module.exports = async function handler(req, res) {
  if (!['GET', 'POST'].includes(req.method)) return json(res, 405, { error: 'method_not_allowed' })
  if (req.method === 'POST' && !sameOrigin(req)) return json(res, 403, { error: 'origin_not_allowed' })
  const patient = await requirePatient(req, res)
  if (!patient) return

  try {
    if (req.method === 'GET') {
      const result = await dataPayload(patientDataFetchFor(patient, 'patient_questions?select=id,text,created_at&order=created_at.desc'))
      if (!result.response.ok) return json(res, 503, { error: 'patient_data_unavailable', message: 'Your questions are temporarily unavailable.' })
      return json(res, 200, { items: Array.isArray(result.payload) ? result.payload.map(publicQuestion) : [] })
    }

    const text = String(req.body?.text || '').trim().slice(0, MAX_QUESTION_LENGTH)
    if (!text) return json(res, 422, { error: 'invalid_question', message: 'Write a question first.' })
    const result = await dataPayload(patientDataFetchFor(patient, 'patient_questions', {
      method: 'POST',
      headers: { Prefer: 'return=representation' },
      body: JSON.stringify({ patient_id: patient.user.id, text })
    }))
    if (!result.response.ok || !Array.isArray(result.payload) || !result.payload[0]) {
      return json(res, 400, { error: 'question_not_saved', message: providerMessage(result.payload, 'Your question could not be saved.') })
    }
    return json(res, 201, publicQuestion(result.payload[0]))
  } catch (error) {
    console.error('Patient questions request failed:', error.message)
    return json(res, 503, { error: 'patient_data_unavailable', message: 'Your questions are temporarily unavailable.' })
  }
}
