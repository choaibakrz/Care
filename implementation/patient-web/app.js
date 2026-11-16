/* Care patient companion. All dynamic text goes through textContent. */
import { COPY as BASE_COPY, RTL } from './copy.js'
import { COPY_DAY } from './copy-day.js'
import { createDay } from './day.js'
import { addRequest, listRequests, saveMood } from './patient-api.js'
import { createBreathing, createMemory, createSounds } from './pause.js'
import { createTranslate } from './translate.js'

const COPY = Object.fromEntries(Object.keys(BASE_COPY).map((lang) => [lang, { ...BASE_COPY[lang], ...COPY_DAY[lang] }]))

const REQUESTS = {
  water: { icon: 'i-water', tone: 'tone-sky', label: 'water', person: false },
  blanket: { icon: 'i-blanket', tone: 'tone-sun', label: 'blanket', person: false },
  wheelchair: { icon: 'i-wheelchair', tone: 'tone-sage', label: 'wheelchair', person: false },
  pain: { icon: 'i-pain', tone: 'tone-rose', label: 'pain', person: true },
  interpreter: { icon: 'i-language', tone: 'tone-lilac', label: 'interpreter', person: true },
  'care-team': { icon: 'i-nurse', tone: 'tone-teal', label: 'careTeamRequest', person: true }
}
const THEME_MODES = ['auto', 'light', 'dark']
const DEFAULT_NAME = 'Patient'
const SOS_HOLD_MS = 5000
const EMERGENCY_NUMBER = (document.body.dataset.emergencyNumber || '112').replace(/[^\d+]/g, '') || '112'
// Only phones and tablets can place the call. On a laptop, opening tel: shows a blocking
// "open external app" prompt, so it only shows the alert and the call link.
const CAN_DIAL = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)

function pickLanguage() {
  const preferred = (navigator.language || 'en').slice(0, 2).toLowerCase()
  return COPY[preferred] ? preferred : 'en'
}

const root = document.documentElement
const state = {
  language: pickLanguage(),
  themeMode: THEME_MODES.includes(root.dataset.themeMode) ? root.dataset.themeMode : 'auto',
  theme: root.dataset.theme === 'dark' ? 'dark' : 'light',
  firstName: DEFAULT_NAME,
  patientAssigned: false,
  mode: 'room',
  accountContact: '',
  room: null,
  device: null,
  mood: null,
  requests: [],
  activeRequestId: null,
  toastTimer: null,
  sosPressing: false,
  sosStartedAt: 0,
  sosTimer: null,
  sosProgressTimer: null,
  sosActive: false,
  sosSilenced: false,
  sosAudio: null,
  sosAlarmTimer: null
}
const $ = (selector) => document.querySelector(selector)
const $$ = (selector) => [...document.querySelectorAll(selector)]
const copy = () => COPY[state.language]
const modules = {}

function daypart(date = new Date()) {
  const hour = date.getHours()
  if (hour >= 5 && hour < 12) return 'morning'
  if (hour >= 12 && hour < 18) return 'afternoon'
  if (hour >= 18 && hour < 22) return 'evening'
  return 'night'
}

function timeLabel(timestamp) {
  return new Intl.DateTimeFormat(state.language, { hour: '2-digit', minute: '2-digit' }).format(timestamp)
}

function useIcon(target, id) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'ic')
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use')
  use.setAttribute('href', `#${id}`)
  svg.append(use)
  target.replaceChildren(svg)
}

/* ---------- language & greeting ---------- */
function renderGreeting() {
  const part = daypart()
  root.dataset.daypart = part
  const text = copy().greetings[part].replace('{name}', state.firstName || DEFAULT_NAME)
  $('#greeting-text').textContent = text
  $('#greeting-line').textContent = copy().greetingLines[part]
  const role = document.querySelector('[data-i18n="nurseRole"]')
  const avatar = document.querySelector('.team-avatar')
  if (avatar) avatar.textContent = [...copy().nurseName][0]
  if (role) role.textContent = part === 'evening' || part === 'night' ? copy().nurseRoleNight : copy().nurseRole
}

function renderRoomDetails() {
  const c = copy()
  const account = state.mode === 'account'
  const roomLabel = state.room?.label || c.rdRoomNone
  const wing = state.room?.wing || c.rdWaiting
  const floor = Number.isFinite(state.room?.floor) && wing !== `Floor ${state.room.floor}` ? ` · ${c.rdFloor.replace('{n}', state.room.floor)}` : ''
  $('#patient-room-label').textContent = account ? c.rdAccount : roomLabel
  $('#patient-room-wing').textContent = account ? (state.accountContact || c.rdSignedIn) : `${wing}${floor}`
  $('#profile-patient').textContent = state.patientAssigned ? state.firstName : c.rdNoPatient
  $('#profile-room').textContent = `${roomLabel} · ${wing}${floor}`
  $('#profile-device').textContent = state.device?.label || c.rdNotPaired
  $('#profile-open-label').textContent = account ? c.editName : c.rdRoomDetails
  $('#profile-open-icon use').setAttribute('href', account ? '#i-pencil' : '#i-pin')
  $('#profile-account-section').hidden = !account
  $('#profile-room-section').hidden = account
  $('#profile-dialog-title').textContent = account ? c.profileTitle : c.rdRoomConnection
  $('#profile-dialog-body').textContent = account ? c.profileBody : c.rdRoomBody
  $('#profile-email').textContent = state.accountContact || '—'
  const logout = $('#logout-button')
  if (!logout.disabled) logout.textContent = account ? c.signOut : c.rdDisconnect
}

function applyLanguage() {
  root.lang = state.language
  root.dir = RTL.has(state.language) ? 'rtl' : 'ltr'
  $('#language-select').value = state.language
  $$('[data-i18n]').forEach((element) => {
    const value = copy()[element.dataset.i18n]
    if (typeof value === 'string') element.textContent = value
  })
  $$('[data-i18n-placeholder]').forEach((element) => {
    const value = copy()[element.dataset.i18nPlaceholder]
    if (typeof value === 'string') element.setAttribute('placeholder', value)
  })
  document.title = `Care · ${copy().tagline}`
  renderGreeting()
  renderRoomDetails()
  renderMoodReply()
  updateStatus()
  renderHistory()
  updateThemeControl()
  updateSosButton()
  modules.day?.refresh()
  modules.breathing?.refresh()
  modules.memory?.refresh()
  modules.translate?.refresh()
}

function setFirstName(firstName) {
  state.firstName = firstName || DEFAULT_NAME
  renderGreeting()
}

/* ---------- theme ---------- */
function automaticTheme(date = new Date()) {
  const hour = date.getHours()
  return hour >= 7 && hour < 19 ? 'light' : 'dark'
}

function updateThemeControl() {
  $('#theme-mode-select').value = state.themeMode
  document.querySelector('meta[name="theme-color"]').setAttribute('content', state.theme === 'dark' ? '#1b1714' : '#faf6f0')
}

function setThemeMode(mode, persist = true) {
  state.themeMode = THEME_MODES.includes(mode) ? mode : 'auto'
  state.theme = state.themeMode === 'auto' ? automaticTheme() : state.themeMode
  root.dataset.theme = state.theme
  root.dataset.themeMode = state.themeMode
  if (persist) {
    try { localStorage.setItem('spectrum-theme-mode', state.themeMode) } catch { /* theme still works without storage */ }
  }
  updateThemeControl()
}

function syncClock() {
  if (state.themeMode === 'auto' && state.theme !== automaticTheme()) setThemeMode('auto', false)
  if (root.dataset.daypart !== daypart()) renderGreeting()
}

/* ---------- emergency SOS ---------- */
function updateSosButton() {
  const button = $('#sos-button')
  const label = $('#sos-button-label')
  if (!button || !label) return
  if (state.sosActive) label.textContent = copy().sosActive
  else if (state.sosPressing) {
    const seconds = Math.max(1, Math.ceil((SOS_HOLD_MS - (performance.now() - state.sosStartedAt)) / 1000))
    label.textContent = copy().sosHolding.replace('{seconds}', String(seconds))
  } else label.textContent = copy().sosLabel
  button.classList.toggle('is-pressing', state.sosPressing)
  button.classList.toggle('is-active', state.sosActive)
  button.setAttribute('aria-pressed', String(state.sosActive))
  button.setAttribute('aria-label', label.textContent)
}

function updateSosProgress() {
  if (!state.sosPressing) return
  const progress = Math.min((performance.now() - state.sosStartedAt) / SOS_HOLD_MS, 1)
  $('#sos-button')?.style.setProperty('--sos-progress', String(progress))
  updateSosButton()
}

function clearSosPress() {
  window.clearTimeout(state.sosTimer)
  window.clearInterval(state.sosProgressTimer)
  state.sosTimer = null
  state.sosProgressTimer = null
  state.sosPressing = false
  state.sosStartedAt = 0
  const button = $('#sos-button')
  button?.style.setProperty('--sos-progress', '0')
  updateSosButton()
}

function beginSosPress(event) {
  if (state.sosActive || state.sosPressing) return
  if (event.type === 'keydown' && event.repeat) return
  if (event.cancelable) event.preventDefault()
  state.sosPressing = true
  state.sosStartedAt = performance.now()
  const button = $('#sos-button')
  if (Number.isInteger(event.pointerId)) {
    try { button.setPointerCapture(event.pointerId) } catch { /* pointer capture is optional */ }
  }
  updateSosButton()
  state.sosProgressTimer = window.setInterval(updateSosProgress, 50)
  state.sosTimer = window.setTimeout(triggerSos, SOS_HOLD_MS)
}

function stopSosPress(event) {
  if (event?.type === 'keyup' && ![' ', 'Enter'].includes(event.key)) return
  if (!state.sosPressing || state.sosActive) return
  clearSosPress()
}

async function startSosAlarm() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext
    if (!AudioContext) return
    const context = new AudioContext()
    await context.resume()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    oscillator.type = 'square'
    oscillator.frequency.value = 880
    gain.gain.value = 0.55
    oscillator.connect(gain).connect(context.destination)
    oscillator.start()
    state.sosAudio = { context, oscillator, gain }
    let high = true
    state.sosAlarmTimer = window.setInterval(() => {
      high = !high
      oscillator.frequency.setTargetAtTime(high ? 880 : 620, context.currentTime, 0.04)
    }, 650)
  } catch {
    // The visual alert and the emergency call remain available if audio is blocked.
  }
}

function silenceSosAlarm() {
  window.clearInterval(state.sosAlarmTimer)
  state.sosAlarmTimer = null
  const audio = state.sosAudio
  state.sosAudio = null
  if (audio) {
    try {
      audio.gain.gain.setTargetAtTime(0.0001, audio.context.currentTime, 0.04)
      audio.oscillator.stop(audio.context.currentTime + 0.08)
      window.setTimeout(() => { void audio.context.close() }, 120)
    } catch { /* audio may already be closed */ }
  }
  state.sosSilenced = true
  $('#sos-stop').disabled = true
  const status = $('#sos-alert-status')
  status.textContent = copy().sosAlarmStopped
  status.hidden = false
}

function triggerSos() {
  clearSosPress()
  state.sosActive = true
  state.sosSilenced = false
  root.dataset.sos = 'active'
  const alert = $('#sos-alert')
  const call = $('#sos-call')
  const number = $('#sos-number')
  alert.hidden = false
  call.href = `tel:${EMERGENCY_NUMBER}`
  number.textContent = EMERGENCY_NUMBER
  $('#sos-stop').disabled = false
  $('#sos-alert-status').hidden = true
  updateSosButton()
  void startSosAlarm()
  // Best effort: mobile browsers hand this to the phone dialler. The visible link is the fallback.
  if (CAN_DIAL) window.setTimeout(() => { window.location.href = `tel:${EMERGENCY_NUMBER}` }, 250)
}

/* ---------- dialogs, toast, views ---------- */
function openDialog(id) { const dialog = $(id); if (dialog && !dialog.open) dialog.showModal() }
function closeDialog(id) { const dialog = $(id); if (dialog?.open) dialog.close() }

function notify(message) {
  const toast = $('#toast')
  toast.textContent = message
  toast.hidden = false
  window.clearTimeout(state.toastTimer)
  state.toastTimer = window.setTimeout(() => { toast.hidden = true }, 4500)
}

function setView(view) {
  if (view !== 'pause') { modules.breathing?.stop(); modules.sounds?.stop() }
  if (view !== 'translate') modules.translate?.stop()
  $$('.view').forEach((element) => { element.hidden = element.id !== `view-${view}` })
  $$('.nav-item').forEach((button) => {
    const active = button.dataset.view === view
    button.classList.toggle('is-active', active)
    if (active) button.setAttribute('aria-current', 'page')
    else button.removeAttribute('aria-current')
  })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/* ---------- mood check-in ---------- */
function setMood(value) {
  if (!state.patientAssigned) {
    notify('No patient is assigned to this room yet. Ask the care team.')
    return
  }
  state.mood = value
  $$('.mood-option').forEach((option) => option.setAttribute('aria-checked', String(Number(option.dataset.mood) === value)))
  renderMoodReply()
  saveMood(value).catch(() => notify(copy().requestError))
}

function renderMoodReply() {
  const reply = $('#mood-reply')
  if (!state.mood) { reply.hidden = true; return }
  reply.hidden = false
  $('#mood-reply-text').textContent = copy().moodReplies[state.mood - 1]
  $('#mood-call').hidden = state.mood > 2
}

/* ---------- requests ---------- */
function requestLabel(request) { return copy()[REQUESTS[request.kind]?.label ?? 'careTeamRequest'] }

function requestStatusIndex(request) {
  if (Number.isInteger(request.statusIndex)) return request.statusIndex
  return { sent: 0, seen: 1, on_the_way: 2, done: 3 }[request.status] ?? 0
}

function requestNote(request) {
  const notes = REQUESTS[request.kind]?.person ? copy().statusNotesPerson : copy().statusNotesItem
  return notes[requestStatusIndex(request)]
}

async function createRequest(kind) {
  if (!state.patientAssigned) {
    notify('No patient is assigned to this room yet.')
    return
  }
  try {
    const request = await addRequest(kind)
    state.requests = [request, ...state.requests.filter((item) => item.id !== request.id)]
    state.activeRequestId = request.id
    updateStatus()
    renderHistory()
    notify(kind === 'pain' ? copy().painSent : `${requestLabel(request)} · ${copy().requestSent}`)
  } catch {
    notify(copy().requestError)
  }
}

async function loadRequests() {
  if (!state.patientAssigned) {
    state.requests = []
    state.activeRequestId = null
    updateStatus()
    renderHistory()
    return
  }
  try {
    state.requests = await listRequests()
    if (!state.requests.some((request) => request.id === state.activeRequestId)) state.activeRequestId = state.requests[0]?.id ?? null
    updateStatus()
    renderHistory()
  } catch {
    // Keep the last successful day visible if the connection briefly drops.
  }
}

function updateStatus() {
  const request = state.requests.find((item) => item.id === state.activeRequestId)
  const status = request ? requestStatusIndex(request) : 0
  $('#active-empty').hidden = Boolean(request)
  $('#active-content').hidden = !request
  $('#live-pill').hidden = !request || status === 3
  if (!request) return
  const meta = REQUESTS[request.kind] ?? REQUESTS['care-team']
  const icon = $('#active-icon')
  icon.className = `summary-icon ${meta.tone}`
  useIcon(icon, meta.icon)
  $('#active-title').textContent = requestLabel(request)
  $('#active-meta').textContent = copy().sentAt.replace('{time}', timeLabel(request.createdAt))
  $('#status-note').textContent = requestNote(request)
  $$('.timeline-step').forEach((step) => {
    const index = Number(step.dataset.step)
    step.classList.toggle('is-complete', index < status || status === 3)
    step.classList.toggle('is-current', index === status && status < 3)
  })
}

function historyRow(request) {
  const meta = REQUESTS[request.kind] ?? REQUESTS['care-team']
  const row = document.createElement('button')
  row.type = 'button'
  row.className = 'history-row'
  row.addEventListener('click', () => { state.activeRequestId = request.id; setView('home'); updateStatus() })
  const icon = document.createElement('span')
  icon.className = `request-icon ${meta.tone}`
  useIcon(icon, meta.icon)
  const details = document.createElement('span')
  const title = document.createElement('strong'); title.textContent = requestLabel(request)
  const time = document.createElement('small'); time.textContent = copy().sentAt.replace('{time}', timeLabel(request.createdAt))
  details.append(title, time)
  const status = document.createElement('span')
  const statusIndex = requestStatusIndex(request)
  status.className = `history-status${statusIndex === 3 ? ' is-done' : ''}`
  status.textContent = copy().statuses[statusIndex]
  row.append(icon, details, status)
  return row
}

function renderHistory() {
  const open = state.requests.filter((request) => requestStatusIndex(request) < 3).length
  $('#request-count').textContent = String(state.requests.length)
  $('#nav-count').textContent = String(open)
  $('#nav-count').hidden = open === 0
  if (state.requests.length === 0) return
  $('#request-history').replaceChildren(...state.requests.map(historyRow))
}

/* ---------- profile ---------- */
function openProfileDialog() {
  renderRoomDetails()
  $('#profile-message').hidden = true
  openDialog('#profile-dialog')
  if (state.mode === 'account') {
    $('#profile-first-name').value = state.firstName === DEFAULT_NAME ? '' : state.firstName
    $('#profile-first-name').focus()
  }
}

function showProfileMessage(text) {
  const message = $('#profile-message')
  message.textContent = text
  message.hidden = !text
}

async function saveProfile(event) {
  // The close button also submits this dialog form: let it close the dialog.
  if (event.submitter?.value === 'cancel') return
  event.preventDefault()
  if (state.mode !== 'account') { closeDialog('#profile-dialog'); return }
  const firstName = $('#profile-first-name').value.trim()
  if (!firstName) { showProfileMessage(copy().nameRequired); $('#profile-first-name').focus(); return }
  const button = $('#profile-save')
  button.disabled = true
  showProfileMessage('')
  try {
    const response = await fetch('/api/auth/profile', {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ first_name: firstName })
    })
    const payload = await response.json().catch(() => ({}))
    if (response.status === 401) { window.location.replace('./login.html'); return }
    if (!response.ok) throw new Error(typeof payload.message === 'string' ? payload.message : copy().nameError)
    setFirstName(payload.user?.firstName || firstName)
    closeDialog('#profile-dialog')
    notify(copy().nameSaved)
  } catch (error) {
    showProfileMessage(error instanceof Error && error.message && !(error instanceof TypeError) ? error.message : copy().nameError)
  } finally {
    button.disabled = false
  }
}

async function signOut() {
  const button = $('#logout-button')
  const account = state.mode === 'account'
  button.disabled = true
  button.textContent = account ? copy().signingOut : 'Disconnecting…'
  showProfileMessage('')
  try {
    const response = await fetch(account ? '/api/auth/logout' : '/api/room/unpair', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    })
    if (!response.ok) throw new Error(copy().logoutError)
    window.location.replace('./login.html')
  } catch {
    showProfileMessage(copy().logoutError)
    button.disabled = false
    button.textContent = account ? copy().signOut : 'Disconnect this tablet'
  }
}

async function loadSessionProfile() {
  const session = await (window.spectrumSessionPromise || Promise.resolve(null))
  if (session?.mode === 'account') {
    state.mode = 'account'
    state.accountContact = session.user?.email || session.user?.phone || ''
    state.patientAssigned = Boolean(session.user?.id)
    setFirstName(session.user?.firstName || DEFAULT_NAME)
  } else {
    state.mode = 'room'
    state.room = session?.room || null
    state.device = session?.device || null
    state.patientAssigned = Boolean(session?.patient?.id)
    setFirstName(session?.patient?.firstName || DEFAULT_NAME)
    if (session?.mode === 'offline') notify('Iris cannot be reached right now. Please check the Wi-Fi connection.')
  }
  renderRoomDetails()
  void loadRequests()
}

/* ---------- events ---------- */
document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-action], [data-choice], [data-view], [data-mood], #header-help, #support-help, #privacy-toggle, #support-privacy, #mood-call')
  if (!target) return
  if (target.dataset.view) {
    if (target.dataset.trMode) modules.translate?.setMode(target.dataset.trMode)
    setView(target.dataset.view)
    return
  }
  if (target.dataset.mood) { setMood(Number(target.dataset.mood)); return }
  if (target.id === 'mood-call') { void createRequest('care-team'); $('#mood-call').hidden = true; return }
  if (target.id === 'header-help' || target.id === 'support-help') { openDialog('#help-dialog'); return }
  if (target.id === 'privacy-toggle' || target.id === 'support-privacy') { notify(copy().privacyDetailsToast); return }
  if (target.dataset.choice) { closeDialog('#request-dialog'); void createRequest(target.dataset.choice); return }
  if (target.dataset.action === 'interpreter') { void createRequest('interpreter'); return }
  if (target.dataset.action === 'request') {
    const kind = target.dataset.request
    if (REQUESTS[kind]) void createRequest(kind)
    else openDialog('#request-dialog')
  }
})

$('#language-select').addEventListener('change', (event) => { state.language = COPY[event.target.value] ? event.target.value : 'en'; applyLanguage() })
$('#theme-mode-select').addEventListener('change', (event) => setThemeMode(event.target.value))
$('#profile-open').addEventListener('click', openProfileDialog)
$('#header-profile').addEventListener('click', openProfileDialog)
$('#profile-form').addEventListener('submit', saveProfile)
$('#logout-button').addEventListener('click', signOut)
$('#sos-button').addEventListener('pointerdown', beginSosPress)
$('#sos-button').addEventListener('pointerup', stopSosPress)
$('#sos-button').addEventListener('pointercancel', stopSosPress)
$('#sos-button').addEventListener('keydown', beginSosPress)
$('#sos-button').addEventListener('keyup', stopSosPress)
$('#sos-stop').addEventListener('click', silenceSosAlarm)
window.addEventListener('blur', () => stopSosPress())
$$('.dialog').forEach((dialog) => dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close() }))

const sessionHasPatient = (window.spectrumSessionPromise || Promise.resolve(null))
  .then((session) => session?.mode === 'account' || Boolean(session?.patient?.id) || session?.mode === 'offline')
modules.day = createDay({ t: copy, notify, language: () => state.language, hasPatient: sessionHasPatient })
modules.breathing = createBreathing({ circle: $('#breathe-circle'), label: $('#breathe-label'), button: $('#breathe-button'), t: copy })
modules.memory = createMemory({ board: $('#memory-board'), status: $('#memory-status'), restart: $('#memory-restart'), t: copy })
modules.sounds = createSounds({ buttons: $$('.sound-button'), stopButton: $('#sound-stop') })
modules.translate = createTranslate({ t: copy, notify, language: () => state.language })

applyLanguage()
syncClock()
window.setInterval(syncClock, 60000)
document.addEventListener('visibilitychange', () => { if (!document.hidden) syncClock() })
void loadSessionProfile()
window.setInterval(() => { void loadRequests() }, 15000)
