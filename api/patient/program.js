const {
  dataPayload,
  json,
  providerMessage,
  publicProgramItem,
  patientDataFetchFor,
  requestDate,
  requirePatient,
  rpcFetch
} = require('./_patient')

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') return json(res, 405, { error: 'method_not_allowed' })
  const patient = await requirePatient(req, res)
  if (!patient) return

  try {
    const date = requestDate(req)
    if (patient.mode === 'room') {
      const existing = await dataPayload(patientDataFetchFor(patient, `patient_day_items?select=time,kind,until_time&service_date=eq.${date}&order=time`))
      if (!existing.response.ok) return json(res, 503, { error: 'patient_data_unavailable', message: 'The daily plan is temporarily unavailable.' })
      let rows = Array.isArray(existing.payload) ? existing.payload : []
      if (!rows.length) {
        const seed = [
          ['07:30', 'breakfast', null],
          ['10:00', 'round', null],
          ['11:00', 'physio', null],
          ['12:00', 'lunch', null],
          ['14:00', 'visits', '20:00'],
          ['18:30', 'dinner', null]
        ].map(([time, kind, until_time]) => ({ patient_id: patient.user.id, service_date: date, time, kind, until_time }))
        const created = await dataPayload(patientDataFetchFor(patient, 'patient_day_items', {
          method: 'POST',
          headers: { Prefer: 'resolution=merge-duplicates,return=representation' },
          body: JSON.stringify(seed)
        }))
        if (!created.response.ok) return json(res, 503, { error: 'patient_data_unavailable', message: 'The daily plan is temporarily unavailable.' })
        rows = Array.isArray(created.payload) ? created.payload : seed
      }
      return json(res, 200, { date, items: rows.map(publicProgramItem), demo: false })
    }
    const seeded = await dataPayload(rpcFetch(patient.accessToken, 'ensure_patient_day', { p_service_date: date }))
    if (!seeded.response.ok) {
      console.error('Patient day seed rejected:', seeded.response.status, seeded.payload)
      return json(res, 503, { error: 'patient_data_unavailable', message: providerMessage(seeded.payload, 'The daily plan is temporarily unavailable.') })
    }
    const rows = Array.isArray(seeded.payload) ? seeded.payload : []
    return json(res, 200, { date, items: rows.map(publicProgramItem), demo: false })
  } catch (error) {
    console.error('Patient day load failed:', error.message)
    return json(res, 503, { error: 'patient_data_unavailable', message: 'The daily plan is temporarily unavailable.' })
  }
}
