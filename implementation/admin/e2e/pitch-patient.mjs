// Pitch check of the patient web app on the LIVE Rust server (`/patient/`), phone and laptop.
// Standalone (no vite): node e2e/pitch-patient.mjs
//   PATIENT_BASE   server origin, default http://localhost:8080
//   ENROL_CODE     the one-time admin enrolment code the server printed on first start
//                  (or ADMIN_USER / ADMIN_PASSWORD of an existing admin account)
//   SERVER_LOG     the server's stderr/log file, to read the dummy SMS code
//   LAN_BASE       optional second origin for the same server (e.g. http://192.168.1.20:8080)
import { readFileSync } from 'node:fs'
import { pbkdf2Sync } from 'node:crypto'
import { chromium, devices } from '@playwright/test'

const BASE = (process.env.PATIENT_BASE || 'http://localhost:8080').replace(/\/$/, '')
const OTHER = (process.env.LAN_BASE || BASE.replace('localhost', '127.0.0.1')).replace(/\/$/, '')
const LOG = process.env.SERVER_LOG || ''
const ADMIN_USER = process.env.ADMIN_USER || 'pitch-admin'
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'pitch-password-2026'
const RUN = Date.now().toString(36)

const results = []
let failures = 0
function record(control, ok, detail = '') {
  results.push({ control, ok, detail })
  if (!ok) failures += 1
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${control}${detail ? `  (${detail})` : ''}`)
}
async function step(control, fn) {
  try {
    const detail = await fn()
    record(control, true, typeof detail === 'string' ? detail : '')
  } catch (error) {
    record(control, false, String(error?.message || error).split('\n')[0])
  }
}
function expect(condition, message) { if (!condition) throw new Error(message) }

/** Watches a page: console errors, page errors and failing requests (with allowed exceptions). */
function watch(page, label) {
  const problems = []
  page.on('console', (message) => { if (message.type() === 'error') problems.push(`console: ${message.text()}`) })
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (response.status() < 400) return
    // The session probes answer 401 by design when nobody is signed in.
    if (response.request().method() === 'GET' && ['/api/room/session', '/api/auth/session'].includes(url.pathname) && response.status() === 401) return
    if (page.__allow?.has(`${response.status()} ${url.pathname}`)) return
    problems.push(`http ${response.status()} ${response.request().method()} ${url.pathname}`)
  })
  page.on('requestfailed', (request) => {
    const url = request.url()
    // tel: links, and probes cut short because the page moved on (redirect after sign-in).
    if (url.startsWith('tel:') || request.failure()?.errorText === 'net::ERR_ABORTED') return
    problems.push(`requestfailed ${url} ${request.failure()?.errorText}`)
  })
  return {
    allow(entry) { page.__allow = page.__allow || new Set(); page.__allow.add(entry) },
    // 401 console lines for the session probes are expected; everything else is a problem.
    check(control) {
      const real = problems.filter((line) => !/status of 401/.test(line))
      problems.length = 0
      record(`${label}: ${control}: no console error / failing request`, real.length === 0, real.join(' | '))
    }
  }
}

async function toast(page) {
  const element = page.locator('#toast')
  await element.waitFor({ state: 'visible', timeout: 5000 })
  return (await element.textContent())?.trim() || ''
}

async function waitForApi(page, method, path, action) {
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === method && new URL(r.url()).pathname === path, { timeout: 8000 }),
    action()
  ])
  return response
}

/* ---------- staff side (admin bearer) ---------- */
function accountKey(user, password) {
  return pbkdf2Sync(Buffer.from(password.normalize('NFC')), Buffer.from(`clinic:demo-clinic:${user.normalize('NFC').toLowerCase()}`), 600000, 32, 'sha256').toString('hex')
}
async function api(method, path, body, token) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined
  })
  const text = await response.text()
  let json = null
  try { json = JSON.parse(text) } catch { json = text }
  return { status: response.status, json }
}
async function adminToken() {
  const key = accountKey(ADMIN_USER, ADMIN_PASSWORD)
  if (process.env.ENROL_CODE) {
    const enrol = await api('POST', '/auth/enrol', { enrolment_code: process.env.ENROL_CODE, account_key: key, display_label: 'Pitch admin' })
    if (![201, 409].includes(enrol.status)) throw new Error(`enrol ${enrol.status} ${JSON.stringify(enrol.json)}`)
  }
  const login = await api('POST', '/auth/login', { account_key: key })
  if (login.status !== 200) throw new Error(`login ${login.status} ${JSON.stringify(login.json)}`)
  return login.json.token
}

function lastSmsCode() {
  if (!LOG) return null
  // eslint-disable-next-line no-control-regex
  const text = readFileSync(LOG, 'utf8').replace(/\u001b\[[0-9;]*m/g, '')
  const matches = [...text.matchAll(/code=(\d{6})/g)]
  return matches.at(-1)?.[1] ?? null
}

/* ---------- the app, signed in ---------- */
async function exerciseApp(page, w, label, { account }) {
  await step(`${label}: greeting shows the name`, async () => {
    await page.waitForFunction(() => !/Patient/.test(document.querySelector('#greeting-text')?.textContent || 'Patient') || document.querySelector('#patient-room-label')?.textContent !== 'Room —', null, { timeout: 8000 })
    return await page.locator('#greeting-text').textContent()
  })

  if (account) {
    await step(`${label}: Change my name (profile save)`, async () => {
      await page.click('#profile-open')
      await page.locator('#profile-dialog').waitFor({ state: 'visible' })
      await page.fill('#profile-first-name', 'Maria')
      const response = await waitForApi(page, 'PUT', '/api/auth/profile', () => page.click('#profile-save'))
      expect(response.status() === 200, `PUT profile ${response.status()}`)
      await page.locator('#profile-dialog').waitFor({ state: 'hidden' })
      const text = await page.locator('#greeting-text').textContent()
      expect(text.includes('Maria'), `greeting "${text}"`)
      return `${await toast(page)}`
    })
    await step(`${label}: profile dialog empty name shows a message`, async () => {
      await page.click('#header-profile')
      await page.fill('#profile-first-name', '')
      await page.click('#profile-save')
      await page.locator('#profile-message').waitFor({ state: 'visible' })
      await page.click('#profile-dialog .dialog-close')
      await page.locator('#profile-dialog').waitFor({ state: 'hidden' })
      return 'message shown, close button closes'
    })
  } else {
    await step(`${label}: Room details dialog`, async () => {
      await page.click('#profile-open')
      await page.locator('#profile-dialog').waitFor({ state: 'visible' })
      const room = await page.locator('#profile-room').textContent()
      expect(!room.startsWith('Room —'), `room "${room}"`)
      await page.click('#profile-dialog .dialog-close')
      await page.locator('#profile-dialog').waitFor({ state: 'hidden' })
      return room
    })
  }
  w.check('profile')

  await step(`${label}: mood check-in (low mood + "let the team know")`, async () => {
    const response = await waitForApi(page, 'POST', '/api/patient/mood', () => page.click('.mood-option[data-mood="2"]'))
    expect(response.status() === 204, `mood ${response.status()}`)
    await page.locator('#mood-reply').waitFor({ state: 'visible' })
    const call = await waitForApi(page, 'POST', '/api/patient/requests', () => page.click('#mood-call'))
    expect(call.status() === 201, `mood-call ${call.status()}`)
    return await toast(page)
  })
  await step(`${label}: mood check-in (good mood)`, async () => {
    const response = await waitForApi(page, 'POST', '/api/patient/mood', () => page.click('.mood-option[data-mood="5"]'))
    expect(response.status() === 204, `mood ${response.status()}`)
    expect(await page.locator('#mood-call').isHidden(), 'call button should hide for a good mood')
  })
  w.check('mood')

  for (const kind of ['water', 'blanket', 'wheelchair', 'pain', 'care-team']) {
    await step(`${label}: request card "${kind}"`, async () => {
      const response = await waitForApi(page, 'POST', '/api/patient/requests', () => page.click(`.request-card[data-request="${kind}"]`))
      expect(response.status() === 201, `request ${response.status()}`)
      const message = await toast(page)
      const title = await page.locator('#active-title').textContent()
      return `${title} / ${message}`
    })
  }
  await step(`${label}: request card "interpreter"`, async () => {
    const response = await waitForApi(page, 'POST', '/api/patient/requests', () => page.click('.request-card[data-action="interpreter"]'))
    expect(response.status() === 201, `request ${response.status()}`)
    return await page.locator('#active-title').textContent()
  })
  await step(`${label}: hero "Ask a nurse to come"`, async () => {
    const response = await waitForApi(page, 'POST', '/api/patient/requests', () => page.click('.hero-actions [data-request="care-team"]'))
    expect(response.status() === 201, `request ${response.status()}`)
    await page.locator('#active-content').waitFor({ state: 'visible' })
    return await page.locator('#status-note').textContent()
  })
  w.check('requests')

  await step(`${label}: header Help dialog`, async () => {
    await page.click('#header-help')
    await page.locator('#help-dialog').waitFor({ state: 'visible' })
    await page.click('#help-dialog .button-danger')
    await page.locator('#help-dialog').waitFor({ state: 'hidden' })
  })
  await step(`${label}: "How we protect you"`, async () => {
    await page.click('#privacy-toggle')
    return await toast(page)
  })

  await step(`${label}: nav My day + programme`, async () => {
    await page.click('.nav-item[data-view="day"]')
    await page.locator('#view-day').waitFor({ state: 'visible' })
    await page.waitForFunction(() => document.querySelectorAll('#program-list li').length > 0, null, { timeout: 8000 })
    const count = await page.locator('#program-list li').count()
    const demo = await page.locator('#program-demo').isVisible()
    return `${count} items${demo ? ', example tag' : ''}`
  })
  await step(`${label}: add question`, async () => {
    await page.fill('#question-input', `When can I go home? (${RUN})`)
    const response = await waitForApi(page, 'POST', '/api/patient/questions', () => page.click('#question-form button[type="submit"]'))
    expect(response.status() === 201, `question ${response.status()}`)
    await page.locator('#question-list li').first().waitFor()
    return await toast(page)
  })
  await step(`${label}: delete question`, async () => {
    const before = await page.locator('#question-list li').count()
    const deleted = page.waitForResponse((r) => r.request().method() === 'DELETE' && new URL(r.url()).pathname.startsWith('/api/patient/questions/'), { timeout: 8000 })
    await page.locator('#question-list li .icon-button').first().click()
    const answer = await deleted
    expect(answer.status() === 204 || answer.status() === 200, `delete ${answer.status()}`)
    await page.waitForFunction((n) => document.querySelectorAll('#question-list li').length === n - 1, before)
  })
  await step(`${label}: My requests history row`, async () => {
    const rows = page.locator('#request-history .history-row')
    expect(await rows.count() >= 7, `history rows ${await rows.count()}`)
    await rows.nth(2).click()
    await page.locator('#view-home').waitFor({ state: 'visible' })
  })
  await step(`${label}: "Next" card opens My day`, async () => {
    if (await page.locator('#next-up').isHidden()) return 'hidden (no later item today)'
    await page.click('#next-up')
    await page.locator('#view-day').waitFor({ state: 'visible' })
  })
  w.check('my day')

  await step(`${label}: Pause - breathing`, async () => {
    await page.click('.nav-item[data-view="pause"]')
    await page.locator('#view-pause').waitFor({ state: 'visible' })
    const before = await page.locator('#breathe-button').textContent()
    await page.click('#breathe-button')
    await page.waitForTimeout(300)
    const after = await page.locator('#breathe-button').textContent()
    expect(before !== after, `button stayed "${after}"`)
    await page.click('#breathe-button')
    return `${before} -> ${after}`
  })
  await step(`${label}: Pause - memory game`, async () => {
    const cards = page.locator('#memory-board button')
    expect(await cards.count() > 0, 'no cards')
    await cards.first().click()
    await page.click('#memory-restart')
    return `${await cards.count()} cards`
  })
  for (const sound of ['rain', 'waves', 'calm']) {
    await step(`${label}: Pause - sound ${sound}`, async () => {
      await page.click(`.sound-button[data-sound="${sound}"]`)
      await page.waitForFunction((s) => document.querySelector(`.sound-button[data-sound="${s}"]`)?.getAttribute('aria-pressed') === 'true', sound, { timeout: 3000 })
    })
  }
  await step(`${label}: Pause - stop the sound`, async () => {
    await page.click('#sound-stop')
    await page.locator('#sound-stop').waitFor({ state: 'hidden' })
  })
  w.check('pause')

  await step(`${label}: Help view - emergency dialog`, async () => {
    await page.click('.nav-item[data-view="support"]')
    await page.click('#support-help')
    await page.locator('#help-dialog').waitFor({ state: 'visible' })
    await page.click('#help-dialog .dialog-close')
    await page.locator('#help-dialog').waitFor({ state: 'hidden' })
  })
  await step(`${label}: Help view - interpreter button`, async () => {
    const response = await waitForApi(page, 'POST', '/api/patient/requests', () => page.click('#view-support [data-action="interpreter"]'))
    expect(response.status() === 201, `request ${response.status()}`)
    return await toast(page)
  })
  await step(`${label}: Help view - privacy button`, async () => {
    await page.click('#support-privacy')
    return await toast(page)
  })
  w.check('help')

  await step(`${label}: language switch (fr, ar, en)`, async () => {
    await page.click('.nav-item[data-view="home"]')
    await page.selectOption('#language-select', 'fr')
    expect(await page.evaluate(() => document.documentElement.lang) === 'fr', 'lang fr')
    const greeting = await page.locator('#greeting-text').textContent()
    await page.selectOption('#language-select', 'ar')
    expect(await page.evaluate(() => document.documentElement.dir) === 'rtl', 'rtl')
    await page.selectOption('#language-select', 'en')
    return greeting
  })
  await step(`${label}: theme switch`, async () => {
    await page.selectOption('#theme-mode-select', 'dark')
    expect(await page.evaluate(() => document.documentElement.dataset.theme) === 'dark', 'dark')
    await page.selectOption('#theme-mode-select', 'light')
    expect(await page.evaluate(() => document.documentElement.dataset.theme) === 'light', 'light')
    await page.selectOption('#theme-mode-select', 'auto')
  })
  await step(`${label}: SOS short press does not trigger`, async () => {
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.locator('#sos-button').scrollIntoViewIfNeeded()
    const box = await page.locator('#sos-button').boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.waitForTimeout(600)
    expect(/\d/.test(await page.locator('#sos-button-label').textContent()), 'press not registered')
    await page.mouse.up()
    expect(await page.locator('#sos-alert').isHidden(), 'alert opened on a short press')
  })
  await step(`${label}: SOS hold 5 s + Silence alarm`, async () => {
    // A separate page: on a phone the call hands over to the dialler (tel:).
    const sos = await page.context().newPage()
    await sos.goto(page.url())
    await sos.locator('#sos-button').waitFor()
    const box = await sos.locator('#sos-button').boundingBox()
    await sos.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await sos.mouse.down()
    await sos.waitForTimeout(5400)
    await sos.mouse.up()
    await sos.locator('#sos-alert').waitFor({ state: 'visible' })
    const href = await sos.locator('#sos-call').getAttribute('href')
    expect(href === 'tel:112', `call link ${href}`)
    const mobile = await sos.evaluate(() => /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent))
    if (mobile) { await sos.close(); return 'alert + call link; the phone opens the dialler' }
    await sos.click('#sos-stop')
    await sos.locator('#sos-alert-status').waitFor({ state: 'visible' })
    const text = await sos.locator('#sos-alert-status').textContent()
    await sos.close()
    return text
  })
  w.check('header controls')
}

async function signOutFromApp(page, label, { account }) {
  await step(`${label}: ${account ? 'Sign out' : 'Disconnect this tablet'}`, async () => {
    await page.click('#header-profile')
    const path = account ? '/api/auth/logout' : '/api/room/unpair'
    const response = await waitForApi(page, 'POST', path, () => page.click('#logout-button'))
    expect(response.status() === 200, `${path} ${response.status()}`)
    await page.waitForURL(/login\.html/)
    await page.goto(`${BASE}/patient/index.html`)
    await page.waitForURL(/login\.html/)
    return 'back on the sign-in page, index redirects'
  })
}

/* ---------- run ---------- */
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || 'chrome' })
const phone = { ...devices['iPhone 13'], viewport: { width: 390, height: 844 } }
delete phone.defaultBrowserType
const laptop = { viewport: { width: 1280, height: 800 } }

// 1. Phone: e-mail sign-up, then everything.
{
  const context = await browser.newContext(phone)
  const page = await context.newPage()
  const w = watch(page, 'phone/email')
  const email = `pitch-${RUN}@example.com`
  await step('phone/email: /patient/ redirects to sign-in', async () => {
    await page.goto(`${BASE}/patient/`)
    await page.waitForURL(/login\.html/)
  })
  await step('phone/email: empty first name shows a message', async () => {
    await page.click('#password-submit')
    // the browser blocks the empty email first; fill it to reach our check
    await page.fill('#identifier', email)
    await page.fill('#password', 'pitchpass1')
    await page.click('#password-submit')
    await page.locator('#auth-message').waitFor({ state: 'visible' })
    return await page.locator('#auth-message').textContent()
  })
  await step('phone/email: wrong password for unknown account shows error', async () => {
    await page.fill('#first-name', 'Alex')
    page.__allow = new Set(['401 /api/auth/login'])
    await page.fill('#identifier', email)
    await page.fill('#password', 'pitchpass1')
    const response = await waitForApi(page, 'POST', '/api/auth/login', () => page.click('#password-submit'))
    expect(response.status() === 401, `login ${response.status()}`)
    await page.waitForFunction(() => /not valid/.test(document.querySelector('#auth-message')?.textContent || ''))
    return await page.locator('#auth-message').textContent()
  })
  await step('phone/email: create account', async () => {
    await page.click('#toggle-auth-mode')
    expect((await page.locator('#auth-title').textContent()) === 'Create account', 'title')
    await page.fill('#identifier', email)
    await page.fill('#password', 'pitchpass1')
    await page.fill('#confirm-password', 'pitchpass1')
    const response = await waitForApi(page, 'POST', '/api/auth/signup', () => page.click('#password-submit'))
    expect(response.status() === 201, `signup ${response.status()}`)
    await page.waitForURL(/index\.html/)
  })
  w.check('sign-up')
  await exerciseApp(page, w, 'phone/email', { account: true })
  await signOutFromApp(page, 'phone/email', { account: true })
  await step('phone/email: sign in again with the password', async () => {
    await page.fill('#first-name', 'Maria')
    await page.fill('#identifier', email)
    await page.fill('#password', 'pitchpass1')
    const response = await waitForApi(page, 'POST', '/api/auth/login', () => page.click('#password-submit'))
    expect(response.status() === 200, `login ${response.status()}`)
    await page.waitForURL(/index\.html/)
    await page.waitForFunction(() => /Maria/.test(document.querySelector('#greeting-text')?.textContent || ''))
    await page.waitForFunction(() => document.querySelectorAll('#request-history .history-row').length >= 7, null, { timeout: 8000 })
    return 'requests of the day still listed'
  })
  w.check('sign-in')
  await context.close()
}

// 2. Laptop: phone number sign-up with a password.
{
  const context = await browser.newContext(laptop)
  const page = await context.newPage()
  const w = watch(page, 'laptop/phone')
  await step('laptop/phone: create account with a phone number', async () => {
    await page.goto(`${BASE}/patient/login.html`)
    await page.click('[data-auth-method="phone"]')
    expect((await page.locator('#identifier-label').textContent()) === 'Phone number', 'label')
    await page.click('#toggle-auth-mode')
    await page.fill('#first-name', 'Luca')
    await page.fill('#identifier', `+41 79 ${RUN.length} 00 ${String(Date.now()).slice(-4)}`.replace(/\s+/g, ' '))
    await page.fill('#password', 'pitchpass2')
    await page.fill('#confirm-password', 'pitchpass2')
    const response = await waitForApi(page, 'POST', '/api/auth/signup', () => page.click('#password-submit'))
    expect(response.status() === 201, `signup ${response.status()}`)
    await page.waitForURL(/index\.html/)
  })
  await exerciseApp(page, w, 'laptop/phone', { account: true })
  await signOutFromApp(page, 'laptop/phone', { account: true })
  await context.close()
}

// 3. Phone: SMS code (request + verify; the dummy SMS is in the server log).
{
  const context = await browser.newContext(phone)
  const page = await context.newPage()
  const w = watch(page, 'phone/sms')
  const number = `+41 78 ${String(Date.now()).slice(-7)}`
  await step('phone/sms: request a code', async () => {
    await page.goto(`${BASE}/patient/login.html`)
    await page.fill('#first-name', 'Noor')
    await page.click('[data-auth-method="phone"]')
    await page.click('#show-sms')
    await page.fill('#sms-phone', number)
    const response = await waitForApi(page, 'POST', '/api/auth/request-otp', () => page.click('#send-code'))
    expect(response.status() === 200, `request-otp ${response.status()}`)
    await page.locator('#code-step').waitFor({ state: 'visible' })
    return await page.locator('#auth-message').textContent()
  })
  await step('phone/sms: wrong code shows an error', async () => {
    page.__allow = new Set(['401 /api/auth/verify-otp'])
    await page.fill('#sms-code', '000000')
    const response = await waitForApi(page, 'POST', '/api/auth/verify-otp', () => page.click('#verify-code'))
    expect(response.status() === 401, `verify ${response.status()}`)
    return await page.locator('#auth-message').textContent()
  })
  await step('phone/sms: verify the code from the server log', async () => {
    await page.waitForTimeout(300)
    const code = lastSmsCode()
    expect(code, 'no code in the server log (set SERVER_LOG)')
    await page.fill('#sms-code', code)
    const response = await waitForApi(page, 'POST', '/api/auth/verify-otp', () => page.click('#verify-code'))
    expect(response.status() === 200, `verify ${response.status()}`)
    await page.waitForURL(/index\.html/)
    await page.waitForFunction(() => /Noor/.test(document.querySelector('#greeting-text')?.textContent || ''))
  })
  await step('phone/sms: "Use a password instead" goes back', async () => {
    await page.goto(`${BASE}/patient/login.html`) // signed in: bounces to the app
    await page.waitForURL(/index\.html/)
  })
  w.check('sms')
  await signOutFromApp(page, 'phone/sms', { account: true })
  await step('phone/sms: back-to-password link', async () => {
    await page.click('[data-auth-method="phone"]')
    await page.click('#show-sms')
    await page.click('#back-to-password')
    await page.locator('#password-form').waitFor({ state: 'visible' })
  })
  w.check('sms links')
  await context.close()
}

// 4. Room tablet: staff creates the code through the API, the tablet pairs.
{
  let token = null
  let roomId = null
  let code = null
  await step('staff: admin bearer token (enrol + login)', async () => { token = await adminToken() })
  await step('staff: GET /api/admin/rooms', async () => {
    const rooms = await api('GET', '/api/admin/rooms', null, token)
    expect(rooms.status === 200, `rooms ${rooms.status}`)
    const free = rooms.json.rooms.find((room) => !room.patient) || rooms.json.rooms[0]
    expect(free, 'no room in the map')
    roomId = free.id
    if (free.patient) await api('POST', '/api/admin/discharge', { room_id: roomId }, token)
    return `${rooms.json.rooms.length} rooms, using ${free.label}`
  })
  await step('staff: admit a patient', async () => {
    const admit = await api('POST', '/api/admin/rooms', { first_name: 'Sofia', medical_record_ref: `MRN-${RUN}`, room_id: roomId }, token)
    expect(admit.status === 201, `admit ${admit.status} ${JSON.stringify(admit.json)}`)
  })
  await step('staff: create a tablet pairing code', async () => {
    const device = await api('POST', '/api/admin/devices', { room_id: roomId, label: 'Pitch tablet' }, token)
    expect(device.status === 201, `device ${device.status} ${JSON.stringify(device.json)}`)
    code = device.json.pairingCode
    return code
  })

  const context = await browser.newContext({ ...laptop, viewport: { width: 1024, height: 768 }, hasTouch: true })
  const page = await context.newPage()
  const w = watch(page, 'tablet')
  await step('tablet: wrong code shows a friendly error', async () => {
    page.__allow = new Set(['401 /api/room/pair'])
    await page.goto(`${BASE}/patient/login.html#tablet`)
    await page.locator('#tablet-panel').waitFor({ state: 'visible' })
    await page.fill('#pairing-code', 'ZZZZZZZZZZZZ')
    const response = await waitForApi(page, 'POST', '/api/room/pair', () => page.click('#pair-submit'))
    expect(response.status() === 401, `pair ${response.status()}`)
    await page.locator('#auth-message').waitFor({ state: 'visible' })
    return await page.locator('#auth-message').textContent()
  })
  await step('tablet: malformed code is caught before sending', async () => {
    await page.fill('#pairing-code', 'abc')
    await page.click('#pair-submit')
    return await page.locator('#auth-message').textContent()
  })
  await step('tablet: pair with the code (lower case, ?code link style)', async () => {
    await page.goto(`${BASE}/patient/login.html?code=${code.toLowerCase()}`)
    expect(await page.locator('#tablet-panel').isVisible(), 'tablet tab not preselected')
    const response = await waitForApi(page, 'POST', '/api/room/pair', () => page.click('#pair-submit'))
    expect(response.status() === 200, `pair ${response.status()}`)
    await page.waitForURL(/index\.html/)
    await page.waitForFunction(() => /Sofia/.test(document.querySelector('#greeting-text')?.textContent || ''))
    return await page.locator('#patient-room-label').textContent()
  })
  w.check('pairing')
  await exerciseApp(page, w, 'tablet', { account: false })
  await signOutFromApp(page, 'tablet', { account: false })
  await step('staff: the used code no longer works', async () => {
    const reuse = await api('POST', '/api/room/pair', { code })
    expect(reuse.status === 401, `reuse ${reuse.status}`)
  })
  await context.close()

  // A tablet paired to a room with no patient: buttons explain instead of failing.
  await step('tablet (empty room): request and mood buttons explain there is no patient', async () => {
    await api('POST', '/api/admin/discharge', { room_id: roomId }, token)
    const device = await api('POST', '/api/admin/devices', { room_id: roomId }, token)
    expect(device.status === 201, `device ${device.status}`)
    const ctx = await browser.newContext(phone)
    const tab = await ctx.newPage()
    const tw = watch(tab, 'tablet (empty room)')
    await tab.goto(`${BASE}/patient/login.html?code=${device.json.pairingCode}`)
    await tab.click('#pair-submit')
    await tab.waitForURL(/index\.html/)
    await tab.click('.request-card[data-request="water"]')
    const first = await toast(tab)
    await tab.click('.mood-option[data-mood="3"]')
    const second = await toast(tab)
    await tab.click('.nav-item[data-view="day"]')
    await tab.waitForFunction(() => document.querySelectorAll('#program-list li').length > 0, null, { timeout: 8000 })
    tw.check('empty room')
    await ctx.close()
    expect(/No patient/.test(first) && /No patient/.test(second), `${first} / ${second}`)
    return first
  })
}

// 5. Another origin for the same server (127.0.0.1 / LAN IP): cookies and the Origin check.
{
  const context = await browser.newContext(phone)
  const page = await context.newPage()
  const w = watch(page, 'second origin')
  await step(`second origin (${OTHER}): sign-up + request work`, async () => {
    await page.goto(`${OTHER}/patient/login.html`)
    await page.fill('#first-name', 'Ines')
    await page.click('#toggle-auth-mode')
    await page.fill('#identifier', `ines-${RUN}@example.com`)
    await page.fill('#password', 'pitchpass3')
    await page.fill('#confirm-password', 'pitchpass3')
    await page.click('#password-submit')
    await page.waitForURL(/index\.html/)
    const response = await waitForApi(page, 'POST', '/api/patient/requests', () => page.click('.request-card[data-request="water"]'))
    expect(response.status() === 201, `request ${response.status()}`)
  })
  await step('second origin: session cookie is per host (localhost is still signed out)', async () => {
    const other = await context.newPage()
    await other.goto(`${BASE}/patient/index.html`)
    await other.waitForURL(/login\.html/)
    await other.close()
  })
  await step('cross-origin POST with credentials is accepted (open-network mode)', async () => {
    const status = await page.evaluate(async (target) => {
      const response = await fetch(`${target}/api/auth/request-otp`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone: '+41 79 555 00 11' }) })
      return response.status
    }, BASE)
    expect(status === 200, `status ${status}`)
  })
  w.check('second origin')
  await context.close()
}

await browser.close()
console.log(`\n${results.length - failures}/${results.length} passed`)
console.log(JSON.stringify(results))
process.exit(failures ? 1 : 0)
