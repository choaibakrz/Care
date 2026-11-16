// Pitch check of "Translate for me" in the patient app, end to end:
// Chrome's fake microphone plays a WAV -> /api/patient/listen -> clinic-brain (faster-whisper)
// -> Apertus (or scripts/fake_apertus.py) -> the text on the page, read aloud by the clinic voice
// (Piper, today zh only) or, when the answer has no audio, by the browser voice.
// Standalone (no vite): node e2e/pitch-translate.mjs
//   PATIENT_BASE  server origin, default https://localhost:8443 (the microphone needs https)
//   AUDIO_WAV     the speech file the fake microphone plays (16 kHz mono WAV: a phrase, then
//                 a few seconds of silence so the automatic stop can be seen)
//   VOICE_LANG    a target language that has a server voice, default zh
//   BRAIN_DOWN=1  run with clinic-brain stopped: expect the calm "not available" message
//   PW_CHANNEL    browser channel, default chrome
// Screenshots: test-results/translate-*.png
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from '@playwright/test'

const BASE = (process.env.PATIENT_BASE || 'https://localhost:8443').replace(/\/$/, '')
const WAV = process.env.AUDIO_WAV || ''
const VOICE_LANG = process.env.VOICE_LANG || 'zh'
const BRAIN_DOWN = process.env.BRAIN_DOWN === '1'
const RUN = Date.now().toString(36)
const JARGON = "Le patient présente une hypertension artérielle et une dyspnée d'effort; prendre 5 mg deux fois par jour"
const UNAVAILABLE = /not available|isn't available|pas disponible|n'est pas disponible|nicht verfügbar/i
const SHOTS = 'test-results'

let failures = 0
function record(control, ok, detail = '') {
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

if (!WAV || !existsSync(WAV)) {
  console.error('Set AUDIO_WAV to a speech WAV file (see PITCH_RUNBOOK.md).')
  process.exit(2)
}
mkdirSync(SHOTS, { recursive: true })

const browser = await chromium.launch({
  channel: process.env.PW_CHANNEL || 'chrome',
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${WAV}`]
})
// A French phone: navigator.language is fr-FR, so the app and the default target are French.
const context = await browser.newContext({
  ignoreHTTPSErrors: true,
  locale: 'fr-FR',
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
  permissions: ['microphone']
})
// Record every playback and every browser-voice request, so the checks can see what was heard.
await context.addInitScript(() => {
  window.__plays = []
  window.__spoken = []
  const play = HTMLMediaElement.prototype.play
  HTMLMediaElement.prototype.play = function (...args) {
    const entry = { el: this, muted: this.muted, at: performance.now() }
    window.__plays.push(entry)
    return play.apply(this, args)
  }
  if ('speechSynthesis' in window) {
    const speak = window.speechSynthesis.speak.bind(window.speechSynthesis)
    window.speechSynthesis.speak = (utterance) => {
      if (utterance.text.trim()) window.__spoken.push({ text: utterance.text, lang: utterance.lang })
      return speak(utterance)
    }
  }
})
const page = await context.newPage()
const problems = []
page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
// A failed request (503 from /speak) is logged by Chrome as "Failed to load resource": expected.
page.on('console', (message) => {
  if (message.type() === 'error' && !/Failed to load resource/.test(message.text())) problems.push(`console: ${message.text()}`)
})

const shot = (name) => page.screenshot({ path: `${SHOTS}/translate-${name}.png` }).catch(() => {})
const audiblePlays = () => page.evaluate(() => window.__plays.filter((p) => !p.muted && !p.el.muted).length)
async function playedFor(ms) {
  // The last audible playback really advanced (the sound came out, not only play() was called).
  await page.waitForTimeout(ms)
  return page.evaluate(() => {
    const last = window.__plays.filter((p) => !p.muted).at(-1)
    return last ? last.el.currentTime : 0
  })
}

/** Taps the mic once and waits for the automatic stop and the answer (no second tap). */
async function listenAuto(name) {
  const responsePromise = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/patient/listen', { timeout: 45000 })
  const tappedAt = Date.now()
  await page.click('#tr-listen')
  await page.locator('#tr-listen.is-recording').waitFor({ timeout: 5000 })
  await page.waitForTimeout(2500)
  await shot(`${name}-listening`)
  await page.locator('#tr-listen:not(.is-recording)').waitFor({ timeout: 35000 })
  const stoppedAfter = Date.now() - tappedAt
  const response = await responsePromise
  return { status: response.status(), body: await response.json().catch(() => null), stoppedAfter }
}

await step('sign up (e-mail) on https', async () => {
  await page.goto(`${BASE}/patient/login.html`)
  await page.click('#toggle-auth-mode')
  await page.fill('#first-name', 'Sara')
  await page.fill('#identifier', `translate-${RUN}@example.com`)
  await page.fill('#password', 'pitchpass3')
  await page.fill('#confirm-password', 'pitchpass3')
  const [response] = await Promise.all([
    page.waitForResponse((r) => new URL(r.url()).pathname === '/api/auth/signup', { timeout: 8000 }),
    page.click('#password-submit')
  ])
  expect(response.status() === 201, `signup ${response.status()}`)
  await page.waitForURL(/index\.html/)
})

await step('home: two normal tiles, Translate and Make it simple, right after Interpreter', async () => {
  const tile = page.locator('#translate-open')
  await tile.waitFor({ state: 'visible' })
  const box = await tile.boundingBox()
  const nurse = await page.locator('.request-card').first().boundingBox()
  const ids = await page.locator('.request-grid .request-card').evaluateAll((cards) => cards.map((card) => card.id))
  const last = ids.slice(ids.indexOf('translate-open'), ids.indexOf('translate-open') + 2).join(',')
  const afterInterpreter = ids.indexOf('translate-open') === 4
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  await page.screenshot({ path: `${SHOTS}/translate-01-home.png`, fullPage: true }).catch(() => {})
  expect(last === 'translate-open,simplify-open' && afterInterpreter, `request cards ${ids.join(',')}`)
  expect(box.height <= nurse.height * 1.1, `tile ${box.height}px vs card ${nurse.height}px`)
  expect(box.y > nurse.y, 'tile above the existing cards')
  expect(overflow <= 0, `sideways scroll ${overflow}px`)
  return `tile ${Math.round(box.width)}x${Math.round(box.height)} at y=${Math.round(box.y)}, first card y=${Math.round(nurse.y)}`
})

await step('open "Translate for me": target is the phone language', async () => {
  await page.click('#simplify-open')
  await page.locator('#tr-simplify-input').waitFor({ state: 'visible' })
  expect(!(await page.locator('#tr-listen').isVisible()), 'simplify tile shows the mic')
  await shot('02-simplify-mode')
  await page.click('[data-view="home"]')
  await page.click('#translate-open')
  await page.locator('#view-translate').waitFor({ state: 'visible' })
  await page.locator('#tr-listen').waitFor({ state: 'visible' })
  expect(await page.locator('#tr-mode-translate').getAttribute('aria-selected') === 'true', 'translate tab not selected')
  const target = await page.locator('#tr-target').inputValue()
  await shot('02-view')
  expect(target === 'fr', `default target ${target}, expected the device language fr`)
  return `target ${target}`
})

if (BRAIN_DOWN) {
  await step('brain stopped: one tap, calm message, button still usable', async () => {
    const result = await listenAuto('down')
    expect(result.status === 503, `listen ${result.status}`)
    expect(result.body?.error === 'translation_unavailable', `error ${result.body?.error}`)
    const text = (await page.locator('#tr-status').textContent()).trim()
    await shot('down-message')
    expect(UNAVAILABLE.test(text), `status "${text}"`)
    expect(await page.locator('#tr-listen').isEnabled(), 'button stays usable')
    return text
  })
  await step('brain stopped: typed text shows the calm message', async () => {
    await page.click('#tr-mode-simplify')
    await page.fill('#tr-simplify-input', JARGON)
    await page.click('#tr-simplify')
    const toast = page.locator('#toast')
    await toast.waitFor({ state: 'visible', timeout: 8000 })
    const text = await toast.textContent()
    await shot('down-typed')
    expect(UNAVAILABLE.test(text), `toast "${text}"`)
    return text
  })
} else {
  let firstAudio = 0
  await step(`listen into ${VOICE_LANG}: stops by itself, text shown, clinic voice plays`, async () => {
    await page.selectOption('#tr-target', VOICE_LANG)
    const result = await listenAuto('03')
    expect(result.status === 200, `listen ${result.status} ${JSON.stringify(result.body)}`)
    expect(result.stoppedAfter < 20000, `auto stop after ${result.stoppedAfter} ms`)
    await page.locator('#tr-results').waitFor({ state: 'visible', timeout: 10000 })
    const shown = (await page.locator('#tr-yours-text').textContent()).trim()
    expect(shown === result.body.translated?.text, `shown "${shown}"`)
    const audio = result.body.audio
    expect(audio?.mime === 'audio/wav' && audio.data.startsWith('UklGR'), `audio ${JSON.stringify(audio)?.slice(0, 80)}`)
    firstAudio = Math.floor(audio.data.length * 3 / 4)
    const time = await playedFor(1500)
    await shot('04-result-voice')
    expect(time > 0.3, `playback did not advance (currentTime ${time})`)
    return `stopped after ${(result.stoppedAfter / 1000).toFixed(1)} s; heard[${result.body.heard.lang}] "${result.body.heard.text}" -> ${VOICE_LANG} "${shown}"; WAV ${firstAudio} bytes, played ${time.toFixed(2)} s`
  })

  await step('"Play again" plays the voice again', async () => {
    await page.waitForTimeout(2500) // let the first playback end
    const before = await audiblePlays()
    await page.click('#tr-play')
    const time = await playedFor(1200)
    const after = await audiblePlays()
    expect(after > before, 'no new playback')
    expect(time > 0.3, `currentTime ${time}`)
    return `played ${time.toFixed(2)} s`
  })

  await step('"Make it simple" shows plain words and reads them', async () => {
    const before = await audiblePlays()
    const [simplify, speak] = await Promise.all([
      page.waitForResponse((r) => new URL(r.url()).pathname === '/api/patient/simplify', { timeout: 30000 }),
      page.waitForResponse((r) => new URL(r.url()).pathname === '/api/patient/speak', { timeout: 30000 }),
      page.click('#tr-make-simple')
    ])
    expect(simplify.status() === 200, `simplify ${simplify.status()}`)
    expect(speak.status() === 200 && speak.headers()['content-type'] === 'audio/wav', `speak ${speak.status()}`)
    const bytes = Number(speak.headers()['content-length'] || 0) || (await speak.body().catch(() => Buffer.alloc(0))).length
    await page.locator('#tr-simplify-result').waitFor({ state: 'visible' })
    const text = (await page.locator('#tr-simplify-text').textContent()).trim()
    const time = await playedFor(1200)
    await shot('05-simple')
    expect(text.length > 0, 'no simple text')
    expect((await audiblePlays()) > before && time > 0.3, `simple text not played (${time})`)
    return `"${text}"; WAV ${bytes} bytes, played ${time.toFixed(2)} s`
  })

  await step('change the target to French (no server voice): browser voice reads it', async () => {
    await page.selectOption('#tr-target', 'fr')
    await page.evaluate(() => { window.__spoken = [] })
    const result = await listenAuto('06')
    expect(result.status === 200, `listen ${result.status}`)
    expect(result.body.translated?.lang === 'fr', `translated lang ${result.body.translated?.lang}`)
    expect(result.body.audio === null, 'expected audio null for fr')
    await page.waitForFunction((text) => document.querySelector('#tr-yours-text')?.textContent === text, result.body.translated.text, { timeout: 5000 })
    await page.waitForFunction(() => window.__spoken.length > 0, null, { timeout: 5000 })
    const spoken = await page.evaluate(() => window.__spoken.at(-1))
    const status = (await page.locator('#tr-status').textContent()).trim()
    await page.waitForTimeout(1000) // let the smooth scroll to the result end
    await shot('06-result-browser-voice')
    expect(spoken.lang.startsWith('fr') && spoken.text === result.body.translated.text, `spoken ${JSON.stringify(spoken)}`)
    expect(!(await page.locator('#tr-status').evaluate((el) => el.classList.contains('is-error'))), `status is an error: "${status}"`)
    return `-> fr "${spoken.text}" read by the browser in ${spoken.lang}; status "${status}"`
  })

  await step('typed text: "Make it simple" keeps the numbers, read by the browser voice', async () => {
    await page.click('#tr-mode-simplify')
    await page.fill('#tr-simplify-input', JARGON)
    await page.evaluate(() => { window.__spoken = [] })
    const [response, speak] = await Promise.all([
      page.waitForResponse((r) => new URL(r.url()).pathname === '/api/patient/simplify', { timeout: 30000 }),
      page.waitForResponse((r) => new URL(r.url()).pathname === '/api/patient/speak', { timeout: 30000 }),
      page.click('#tr-simplify')
    ])
    expect(response.status() === 200, `simplify ${response.status()}`)
    const voice = await speak.json().catch(() => null)
    expect(speak.status() === 503 && voice?.error === 'voice_unavailable', `speak ${speak.status()} ${JSON.stringify(voice)}`)
    await page.locator('#tr-simplify-result').waitFor({ state: 'visible' })
    const text = (await page.locator('#tr-simplify-text').textContent()).trim()
    await page.waitForFunction(() => window.__spoken.length > 0, null, { timeout: 5000 })
    await page.locator('#tr-simplify-result').scrollIntoViewIfNeeded()
    await shot('07-typed')
    expect(/\b5\s*mg\b/.test(text), `5 mg lost: "${text}"`)
    expect(/deux|2/.test(text), `"deux fois" lost: "${text}"`)
    return `"${text}"`
  })

  await step('leaving the view stops the voice', async () => {
    await page.click('#tr-mode-translate')
    await page.click('#tr-play')
    await page.click('[data-view="home"]')
    const paused = await page.evaluate(() => window.__plays.filter((p) => !p.muted).every((p) => p.el.paused))
    expect(paused, 'audio still playing on Home')
  })
}

await step('no page error', async () => { expect(problems.length === 0, problems.join(' | ')) })
await browser.close()
console.log(failures ? `\n${failures} check(s) failed` : '\nall checks passed')
process.exit(failures ? 1 : 0)
