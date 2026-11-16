/*
 * "Translate for me" (view #view-translate).
 * One big button: the microphone records only between the patient's taps (or until ~2 s of
 * silence, at most 30 s). The clip goes to /api/patient/listen, is turned into text and
 * translated by the clinic's local service, and is never stored. The translation comes back
 * as text and, when a voice exists, as spoken audio that plays at once; otherwise the
 * browser voice reads it. "Make it simple" rewrites the text in plain words and reads it too.
 * All dynamic text goes through textContent.
 */

/** Language names written in their own language (the "Into" list). */
export const LANGUAGES = {
  en: 'English', fr: 'Français', de: 'Deutsch', it: 'Italiano', es: 'Español', pt: 'Português',
  nl: 'Nederlands', ar: 'العربية', tr: 'Türkçe', zh: '中文', ru: 'Русский', uk: 'Українська',
  pl: 'Polski', sq: 'Shqip', sr: 'Srpski', hr: 'Hrvatski', ro: 'Română'
}
const STORAGE_KEY = 'spectrum-translate-to'
const MAX_RECORD_MS = 30000
const SILENCE_STOP_MS = 2000 // stop after this much quiet once someone has spoken
const NO_VOICE_STOP_MS = 10000 // stop if nobody speaks at all
const VOICE_LEVEL = 0.02 // RMS above this counts as voice
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg']

function baseCode(code) {
  return String(code || '').trim().toLowerCase().split(/[-_]/)[0]
}

function deviceLanguage() {
  const code = baseCode(navigator.language)
  return LANGUAGES[code] ? code : 'en'
}

function savedLanguage() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && LANGUAGES[saved]) return saved
  } catch { /* storage unavailable: use the device language */ }
  return deviceLanguage()
}

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') return ''
  return MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function reducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** 0.1 s of silence, used to unlock audio playback during the first tap (iOS Safari). */
function silentWav() {
  const samples = 800
  const view = new DataView(new ArrayBuffer(44 + samples * 2))
  const text = (offset, value) => { for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i)) }
  text(0, 'RIFF'); view.setUint32(4, 36 + samples * 2, true); text(8, 'WAVE'); text(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, 8000, true); view.setUint32(28, 16000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  text(36, 'data'); view.setUint32(40, samples * 2, true)
  return new Blob([view], { type: 'audio/wav' })
}

/** `{ mime, data: base64 }` from the API, or null. */
function decodeAudio(audio) {
  if (!audio || typeof audio.data !== 'string' || !audio.data) return null
  try {
    const binary = atob(audio.data)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
    return new Blob([bytes], { type: typeof audio.mime === 'string' ? audio.mime : 'audio/wav' })
  } catch {
    return null
  }
}

/** A failed call: `code` is the API error code or a local one (offline, http_<status>). */
class TranslateError extends Error {
  constructor(code, status) { super(code); this.code = code; this.status = status }
}

async function send(path, body, contentType) {
  let response
  try {
    response = await fetch(`/api/patient/${path}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': contentType },
      body
    })
  } catch {
    throw new TranslateError('offline', 0)
  }
  if (response.status === 401) {
    window.location.replace('./login.html')
    throw new TranslateError('not_authenticated', 401)
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload) throw new TranslateError(payload?.error || `http_${response.status}`, response.status)
  return payload
}

/** Spoken audio for a text from the clinic voice, or null (no voice, offline, error). */
async function fetchSpeech(text, lang) {
  try {
    const response = await fetch('/api/patient/speak', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'audio/wav', 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 2000), lang })
    })
    if (!response.ok) return null
    const blob = await response.blob()
    return blob.size ? blob : null
  } catch {
    return null
  }
}

/**
 * @param {{ t: () => Record<string, any>, notify: (text: string) => void, language?: () => string }} options
 */
export function createTranslate({ t, notify, language = () => 'en' }) {
  const $ = (selector) => document.querySelector(selector)
  const el = {
    target: $('#tr-target'),
    title: $('#tr-title'),
    body: $('#tr-body'),
    stage: document.querySelector('.tr-stage'),
    typeSection: $('#tr-type'),
    modes: [...document.querySelectorAll('.tr-mode')],
    micWrap: $('#tr-mic-wrap'),
    listen: $('#tr-listen'),
    listenLabel: $('#tr-listen-label'),
    meter: $('#tr-meter'),
    status: $('#tr-status'),
    statusText: $('#tr-status-text'),
    spinner: $('#tr-spinner'),
    results: $('#tr-results'),
    resultLabel: $('#tr-result-label'),
    yoursText: $('#tr-yours-text'),
    play: $('#tr-play'),
    makeSimple: $('#tr-make-simple'),
    makeSimpleLabel: $('#tr-make-simple-label'),
    heardLabel: $('#tr-heard-label'),
    heardText: $('#tr-heard-text'),
    simpleCard: $('#tr-simplify-result'),
    simpleText: $('#tr-simplify-text'),
    simpleNote: $('#tr-simplify-note'),
    simplePlay: $('#tr-simple-play'),
    typeOpen: $('#tr-type-open'),
    typeBox: $('#tr-type-box'),
    simplifyInput: $('#tr-simplify-input'),
    simplify: $('#tr-simplify'),
    simplifyLabel: $('#tr-simplify-btn-label')
  }
  const state = {
    target: savedLanguage(),
    mode: 'translate', // translate | simplify
    phase: 'idle', // idle | recording | working
    recorder: null,
    stream: null,
    chunks: [],
    discard: false,
    stopTimer: null,
    context: null,
    source: null,
    frame: null,
    generation: 0, // bumped when the patient leaves: late answers then do not play
    last: null, // { heard: {text, lang}, translated: {text, lang} | null, blob }
    simple: null, // { text, lang, blob, note }
    status: { key: 'trHintIdle', extra: '', error: false },
    busy: '', // '' | 'result' | 'typed': which "Make it simple" button is working
    player: null,
    playerUrl: '',
    unlocked: false
  }

  /* ---------- target language ---------- */
  el.target.replaceChildren(...Object.entries(LANGUAGES).map(([code, name]) => {
    const option = document.createElement('option')
    option.value = code
    option.lang = code
    option.textContent = name
    return option
  }))
  el.target.value = state.target
  el.target.addEventListener('change', () => {
    state.target = LANGUAGES[el.target.value] ? el.target.value : deviceLanguage()
    try { localStorage.setItem(STORAGE_KEY, state.target) } catch { /* still works without storage */ }
  })

  function languageName(code) {
    if (!code) return ''
    try {
      const name = new Intl.DisplayNames([language()], { type: 'language' }).of(code)
      if (name && name !== code) return name
    } catch { /* older browsers: use the native name */ }
    return LANGUAGES[code] || ''
  }

  /* ---------- status line ---------- */
  function setStatus(key, { extra = '', error = false } = {}) {
    state.status = { key, extra, error }
    renderStatus()
  }

  function renderStatus() {
    const { key, extra, error } = state.status
    el.statusText.textContent = key ? `${t()[key] ?? ''}${extra}` : ''
    el.status.classList.toggle('is-error', error)
    el.spinner.hidden = key !== 'trWorking'
  }

  function errorKey(error) {
    if (!(error instanceof TranslateError)) return 'trErrGeneric'
    if (error.code === 'offline') return 'trErrOffline'
    if (error.code === 'recording_too_long' || error.status === 413) return 'trErrTooLong'
    if (error.code === 'unsupported_language') return 'trErrLanguage'
    if (error.code === 'empty_recording') return 'trErrNothing'
    if (['translation_unavailable', 'translation_timeout'].includes(error.code) || error.status >= 500) return 'trErrUnavailable'
    return 'trErrGeneric'
  }

  function setPhase(phase) {
    state.phase = phase
    renderButton()
  }

  function renderButton() {
    const recording = state.phase === 'recording'
    el.micWrap.classList.toggle('is-recording', recording)
    el.listen.classList.toggle('is-recording', recording)
    el.listen.setAttribute('aria-pressed', String(recording))
    el.listen.disabled = state.phase === 'working'
    el.listenLabel.textContent = recording ? t().trDone : t().trTalk
    el.meter.hidden = !recording
  }

  /* ---------- results ---------- */
  function renderResults() {
    const last = state.last
    el.results.hidden = !last || state.mode !== 'translate'
    if (last) {
      const shown = last.translated || last.heard
      el.yoursText.textContent = shown.text
      el.yoursText.lang = shown.lang || ''
      el.resultLabel.textContent = last.translated ? t().trResultLabel : t().trSaid
      const name = languageName(last.heard.lang)
      el.heardLabel.textContent = name ? t().trHeard.replace('{lang}', name) : ''
      el.heardLabel.hidden = !name
      el.heardText.textContent = last.heard.text
      el.heardText.lang = last.heard.lang || ''
    }
    const simple = state.simple
    el.simpleCard.hidden = !simple || (simple.source === 'typed') !== (state.mode === 'simplify')
    if (simple) {
      el.simpleText.textContent = simple.text
      el.simpleText.lang = simple.lang || ''
      el.simpleNote.textContent = t()[simple.note] ?? ''
    }
    el.makeSimpleLabel.textContent = state.busy === 'result' ? t().trSimplifying : t().trSimplify
    el.simplifyLabel.textContent = state.busy === 'typed' ? t().trSimplifying : t().trSimplify
    el.makeSimple.disabled = state.busy !== ''
    el.simplify.disabled = state.busy !== ''
  }

  function reveal(element) {
    element.scrollIntoView?.({ block: 'nearest', behavior: reducedMotion() ? 'auto' : 'smooth' })
  }

  function renderMode() {
    const simplifying = state.mode === 'simplify'
    el.title.textContent = simplifying ? t().simpTitle : t().trTitle
    el.body.textContent = simplifying ? t().simpBody : t().trBody
    el.title.dataset.i18n = simplifying ? 'simpTitle' : 'trTitle'
    el.body.dataset.i18n = simplifying ? 'simpBody' : 'trBody'
    el.stage.hidden = simplifying
    el.typeSection.hidden = !simplifying
    el.typeOpen.hidden = true
    el.typeBox.hidden = false
    el.modes.forEach((button) => {
      const active = button.dataset.trMode === state.mode
      button.classList.toggle('is-active', active)
      button.setAttribute('aria-selected', String(active))
    })
  }

  function setMode(mode) {
    const next = mode === 'simplify' ? 'simplify' : 'translate'
    if (next === state.mode) { renderMode(); return }
    state.generation += 1
    if (state.phase === 'recording') { state.discard = true; stopRecording() }
    stopPlayback()
    state.mode = next
    if (next === 'simplify' && !el.simplifyInput.value.trim()) {
      const shown = state.last?.translated || state.last?.heard
      if (shown) el.simplifyInput.value = shown.text
    }
    renderMode()
    renderResults()
  }

  el.modes.forEach((button) => button.addEventListener('click', () => setMode(button.dataset.trMode)))

  function refresh() {
    renderMode()
    el.target.setAttribute('aria-label', t().trTargetLabel)
    renderButton()
    renderStatus()
    renderResults()
  }

  /* ---------- playback ---------- */
  // HACKATHON privacy: spoken audio only lives in this page's memory (a blob URL), never stored.
  function player() {
    if (!state.player) {
      state.player = new Audio()
      state.player.preload = 'auto'
      state.player.setAttribute('playsinline', '')
    }
    return state.player
  }

  /** Called inside every tap handler, so later playback is allowed (iOS Safari autoplay rules). */
  function unlockAudio() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext
      if (AudioContext && !state.context) state.context = new AudioContext()
      if (state.context?.state === 'suspended') void state.context.resume().catch(() => {})
    } catch { state.context = null }
    if (state.unlocked) return
    state.unlocked = true
    try {
      const audio = player()
      setPlayerBlob(silentWav())
      audio.muted = true
      void audio.play().then(() => { audio.pause(); audio.muted = false }).catch(() => { audio.muted = false })
    } catch { /* playback falls back to the browser voice */ }
    try {
      if ('speechSynthesis' in window) {
        const hush = new SpeechSynthesisUtterance(' ')
        hush.volume = 0
        window.speechSynthesis.speak(hush)
      }
    } catch { /* no browser voice */ }
  }

  function setPlayerBlob(blob) {
    if (state.playerUrl) URL.revokeObjectURL(state.playerUrl)
    state.playerUrl = URL.createObjectURL(blob)
    player().src = state.playerUrl
  }

  function stopPlayback() {
    if (state.player) {
      state.player.pause()
      state.player.muted = false
    }
    try { window.speechSynthesis?.cancel() } catch { /* nothing to stop */ }
  }

  function speakWithBrowser(text, lang) {
    if (!text || !('speechSynthesis' in window)) return
    try {
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = lang
      const voice = window.speechSynthesis.getVoices().find((item) => baseCode(item.lang) === lang)
      if (voice) utterance.voice = voice
      utterance.rate = 0.95
      window.speechSynthesis.speak(utterance)
    } catch { /* the text is still on screen */ }
  }

  /** Plays the clinic voice when there is one, else the browser voice in that language. */
  async function speak({ blob, text, lang }) {
    stopPlayback()
    if (blob) {
      try {
        setPlayerBlob(blob)
        await player().play()
        return
      } catch { /* fall back to the browser voice */ }
    }
    speakWithBrowser(text, lang)
  }

  /* ---------- recording ---------- */
  function stopLevelMeter() {
    window.cancelAnimationFrame(state.frame)
    state.frame = null
    try { state.source?.disconnect() } catch { /* already gone */ }
    state.source = null
    el.micWrap.style.setProperty('--level', '0')
    el.meter.style.setProperty('--level', '0')
  }

  /** Live level + automatic stop after silence. Decoration only if it cannot start. */
  function startLevelMeter(stream) {
    try {
      const context = state.context
      if (!context) return
      if (context.state === 'suspended') void context.resume().catch(() => {})
      const analyser = context.createAnalyser()
      analyser.fftSize = 1024
      const source = context.createMediaStreamSource(stream)
      source.connect(analyser)
      state.source = source
      const data = new Uint8Array(analyser.fftSize)
      const startedAt = performance.now()
      let lastVoiceAt = startedAt
      let heardVoice = false
      const frame = () => {
        if (state.phase !== 'recording') return
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (const value of data) { const sample = (value - 128) / 128; sum += sample * sample }
        const rms = Math.sqrt(sum / data.length)
        const level = String(Math.min(1, rms * 8))
        el.micWrap.style.setProperty('--level', level)
        el.meter.style.setProperty('--level', level)
        const now = performance.now()
        if (rms > VOICE_LEVEL) { heardVoice = true; lastVoiceAt = now }
        if ((heardVoice && now - lastVoiceAt > SILENCE_STOP_MS) || (!heardVoice && now - startedAt > NO_VOICE_STOP_MS)) {
          stopRecording()
          return
        }
        state.frame = window.requestAnimationFrame(frame)
      }
      frame()
    } catch { /* no auto stop: the patient taps Done, or it stops at 30 s */ }
  }

  function releaseMicrophone() {
    window.clearTimeout(state.stopTimer)
    stopLevelMeter()
    state.stream?.getTracks().forEach((track) => track.stop())
    state.stream = null
  }

  function secureAddress() {
    const port = window.location.port === '8080' ? ':8443' : window.location.port ? `:${window.location.port}` : ''
    return `\nhttps://${window.location.hostname}${port}${window.location.pathname}`
  }

  async function startRecording() {
    stopPlayback()
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setStatus(window.isSecureContext ? 'trErrNoMic' : 'trErrInsecure', { extra: window.isSecureContext ? '' : secureAddress(), error: true })
      return
    }
    setPhase('working') // blocks double taps while the browser asks for the microphone
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    } catch (error) {
      setPhase('idle')
      const name = error?.name
      const key = name === 'NotAllowedError' || name === 'SecurityError' ? 'trErrDenied' : name === 'NotFoundError' || name === 'OverconstrainedError' ? 'trErrNoMic' : 'trErrGeneric'
      setStatus(key, { error: true })
      return
    }
    const mimeType = pickMimeType()
    let recorder
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
    } catch {
      stream.getTracks().forEach((track) => track.stop())
      setPhase('idle')
      setStatus('trErrGeneric', { error: true })
      return
    }
    state.stream = stream
    state.recorder = recorder
    state.chunks = []
    state.discard = false
    recorder.addEventListener('dataavailable', (event) => { if (event.data?.size) state.chunks.push(event.data) })
    recorder.addEventListener('stop', () => {
      releaseMicrophone()
      const type = recorder.mimeType || mimeType || 'audio/webm'
      const blob = new Blob(state.chunks, { type })
      state.chunks = []
      state.recorder = null
      if (state.discard) { setPhase('idle'); setStatus('trHintIdle'); return }
      void upload(blob, type)
    })
    recorder.start()
    setPhase('recording')
    setStatus('trListening')
    state.stopTimer = window.setTimeout(stopRecording, MAX_RECORD_MS)
    startLevelMeter(stream)
  }

  function stopRecording() {
    if (state.phase !== 'recording') return
    setPhase('working')
    setStatus('trWorking')
    try { state.recorder?.stop() } catch { releaseMicrophone(); setPhase('idle'); setStatus('trErrGeneric', { error: true }) }
  }

  async function upload(blob, type) {
    if (!blob.size) { setPhase('idle'); setStatus('trErrNothing', { error: true }); return }
    const generation = state.generation
    setPhase('working')
    setStatus('trWorking')
    try {
      const payload = await send(`listen?to=${encodeURIComponent(state.target)}`, blob, type.split(';')[0])
      const heard = { text: String(payload.heard?.text ?? ''), lang: baseCode(payload.heard?.lang) }
      if (!heard.text.trim()) { setStatus('trErrNothing', { error: true }); return }
      const translated = payload.translated && typeof payload.translated.text === 'string'
        ? { text: payload.translated.text, lang: baseCode(payload.translated.lang) || state.target }
        : null
      const blobAudio = translated ? decodeAudio(payload.audio) : null
      state.last = { heard, translated, blob: blobAudio }
      state.simple = null
      renderResults()
      setStatus(translated ? 'trHintAgain' : 'trNoTranslation', { error: !translated })
      if (generation !== state.generation) return
      reveal(el.results)
      const shown = translated || heard
      void speak({ blob: blobAudio, text: shown.text, lang: shown.lang || state.target })
    } catch (error) {
      setStatus(errorKey(error), { error: true })
    } finally {
      setPhase('idle')
    }
  }

  el.listen.addEventListener('click', () => {
    unlockAudio()
    if (state.phase === 'recording') stopRecording()
    else if (state.phase === 'idle') void startRecording()
  })

  /* ---------- play again ---------- */
  async function playAgain(item) {
    if (!item) return
    if (!item.blob && !item.fetched) {
      item.fetched = true
      item.blob = await fetchSpeech(item.text, item.lang)
    }
    void speak(item)
  }

  el.play.addEventListener('click', () => {
    unlockAudio()
    const last = state.last
    if (!last) return
    const shown = last.translated || last.heard
    if (!last.speech) last.speech = { text: shown.text, lang: shown.lang || state.target, blob: last.blob }
    void playAgain(last.speech)
  })

  el.simplePlay.addEventListener('click', () => {
    unlockAudio()
    void playAgain(state.simple)
  })

  /* ---------- make it simple ---------- */
  async function simplify(text, lang, source) {
    const clean = text.trim().slice(0, 2000)
    if (!clean) { notify(t().trErrEmpty); el.simplifyInput.focus(); return }
    const generation = state.generation
    stopPlayback()
    state.busy = source
    renderResults()
    try {
      const payload = await send('simplify', JSON.stringify({ text: clean, lang }), 'application/json')
      const simpleLang = LANGUAGES[baseCode(payload.lang)] ? baseCode(payload.lang) : lang
      const simple = {
        text: String(payload.text ?? clean),
        lang: simpleLang,
        note: payload.simplified === false ? 'trNotSimplified' : 'trSimplifiedLabel',
        blob: null,
        fetched: true,
        source
      }
      state.simple = simple
      state.busy = ''
      renderResults()
      if (generation !== state.generation) return
      reveal(el.simpleCard)
      simple.blob = await fetchSpeech(simple.text, simple.lang)
      if (generation === state.generation && state.simple === simple) void speak(simple)
    } catch (error) {
      notify(t()[errorKey(error)])
    } finally {
      state.busy = ''
      renderResults()
    }
  }

  el.makeSimple.addEventListener('click', () => {
    unlockAudio()
    const shown = state.last?.translated || state.last?.heard
    if (shown) void simplify(shown.text, shown.lang || state.target, 'result')
  })

  el.typeOpen.addEventListener('click', () => {
    const open = el.typeBox.hidden
    el.typeBox.hidden = !open
    el.typeOpen.setAttribute('aria-expanded', String(open))
    if (open) el.simplifyInput.focus()
  })

  el.simplify.addEventListener('click', () => {
    unlockAudio()
    void simplify(el.simplifyInput.value, state.target, 'typed')
  })

  return {
    refresh,
    setMode,
    /** Stops the microphone and any voice when the patient leaves the view. */
    stop() {
      state.generation += 1
      if (state.phase === 'recording') { state.discard = true; stopRecording() }
      stopPlayback()
    }
  }
}
