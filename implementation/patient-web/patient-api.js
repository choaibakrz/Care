/*
 * Patient data layer. Calls the patient-scoped backend when it exists
 * (`/api/patient/*`, see implementation/BACKEND_A_FAIRE.md) and falls back to
 * in-memory demo data otherwise, so the static preview keeps working.
 * Nothing is stored in the browser.
 */

const MAX_QUESTION_LENGTH = 300
const DEMO_PROGRAM = [
  { time: '07:30', kind: 'breakfast' },
  { time: '10:00', kind: 'round' },
  { time: '11:00', kind: 'physio' },
  { time: '12:00', kind: 'lunch' },
  { time: '14:00', kind: 'visits', until: '20:00' },
  { time: '18:30', kind: 'dinner' }
]
const KNOWN_KINDS = new Set(DEMO_PROGRAM.map((item) => item.kind))

let demoQuestions = []
let demoRequests = []
let demoCounter = 0

function localDateKey() {
  const date = new Date()
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-')
}

async function call(path, options = {}) {
  try {
    const response = await fetch(`/api/patient/${path}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      ...options
    })
    // No patient API here (static preview, or route not deployed yet): use demo data.
    const isEmpty = response.status === 204
    const isJson = (response.headers.get('content-type') || '').includes('application/json')
    if ([404, 405, 501].includes(response.status) || (!isJson && !isEmpty)) return { offline: true }
    if (isEmpty) return { offline: false, payload: null }
    if (response.status === 401) {
      // The session ended (signed out elsewhere, tablet unpaired): sign in again.
      window.location.replace('./login.html')
      throw new Error('Your session has ended. Please sign in again.')
    }
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(typeof payload.message === 'string' ? payload.message : `HTTP ${response.status}`)
    return { offline: false, payload }
  } catch (error) {
    if (error instanceof TypeError) return { offline: true } // network error: no backend here
    throw error
  }
}

function cleanProgram(items) {
  if (!Array.isArray(items)) return []
  return items
    .filter((item) => item && /^\d{2}:\d{2}$/.test(item.time) && KNOWN_KINDS.has(item.kind))
    .map((item) => ({ time: item.time, kind: item.kind, until: /^\d{2}:\d{2}$/.test(item.until) ? item.until : null }))
    .sort((a, b) => a.time.localeCompare(b.time))
}

function cleanQuestion(item) {
  return { id: String(item.id), text: String(item.text ?? '').slice(0, MAX_QUESTION_LENGTH), createdAt: Number(item.created_at ?? item.createdAt ?? Date.now()) }
}

function cleanRequest(item) {
  const status = ['sent', 'seen', 'on_the_way', 'done'].includes(item.status) ? item.status : 'sent'
  return {
    id: String(item.id),
    kind: String(item.kind),
    status,
    statusIndex: Number.isInteger(item.status_index) ? item.status_index : ['sent', 'seen', 'on_the_way', 'done'].indexOf(status),
    createdAt: Number(item.created_at ?? item.createdAt ?? Date.now()),
    updatedAt: Number(item.updated_at ?? item.updatedAt ?? Date.now())
  }
}

/** The example day, shown while no patient is assigned (nothing is asked from the server). */
export function exampleDayProgram() {
  return { items: cleanProgram(DEMO_PROGRAM), demo: true }
}

/** @returns {Promise<{ items: Array<{time: string, kind: string, until: string|null}>, demo: boolean }>} */
export async function getDayProgram() {
  let result
  try {
    result = await call(`program?date=${localDateKey()}`)
  } catch {
    // No patient in this room yet, or the day is unavailable: show the example day.
    result = { offline: true }
  }
  if (result.offline) return { items: cleanProgram(DEMO_PROGRAM), demo: true }
  return { items: cleanProgram(result.payload.items), demo: Boolean(result.payload.demo) }
}

/** @returns {Promise<Array<{id: string, text: string, createdAt: number}>>} */
export async function listQuestions() {
  const result = await call('questions')
  if (result.offline) return [...demoQuestions]
  return Array.isArray(result.payload.items) ? result.payload.items.map(cleanQuestion) : []
}

/** @param {string} text */
export async function addQuestion(text) {
  const clean = text.trim().slice(0, MAX_QUESTION_LENGTH)
  if (!clean) throw new Error('empty')
  const result = await call('questions', { method: 'POST', body: JSON.stringify({ text: clean }) })
  if (!result.offline) return cleanQuestion(result.payload)
  const question = { id: `demo-${++demoCounter}`, text: clean, createdAt: Date.now() }
  demoQuestions = [...demoQuestions, question]
  return question
}

/** @param {string} id */
export async function removeQuestion(id) {
  const result = await call(`questions/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (result.offline) demoQuestions = demoQuestions.filter((question) => question.id !== id)
}

/** @returns {Promise<Array<{id: string, kind: string, status: string, statusIndex: number, createdAt: number}>>} */
export async function listRequests() {
  const result = await call(`requests?date=${localDateKey()}`)
  if (result.offline) return [...demoRequests]
  return Array.isArray(result.payload.items) ? result.payload.items.map(cleanRequest) : []
}

/** @param {string} kind */
export async function addRequest(kind) {
  const result = await call(`requests?date=${localDateKey()}`, { method: 'POST', body: JSON.stringify({ kind }) })
  if (!result.offline) return cleanRequest(result.payload)
  const request = { id: `demo-request-${++demoCounter}`, kind, status: 'sent', statusIndex: 0, createdAt: Date.now(), updatedAt: Date.now() }
  demoRequests = [request, ...demoRequests]
  return request
}

/** @param {number} value */
export async function saveMood(value) {
  await call(`mood?date=${localDateKey()}`, { method: 'POST', body: JSON.stringify({ value }) })
}

export { MAX_QUESTION_LENGTH }
