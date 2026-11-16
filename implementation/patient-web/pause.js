/*
 * "Pause" tab: guided breathing, a calm memory game and soothing sounds.
 * Everything runs in the browser: no file, no network, no score sent anywhere.
 */

const BREATH_IN_MS = 4000
const BREATH_OUT_MS = 6000
const MEMORY_ICONS = ['i-water', 'i-blanket', 'i-heart-solid', 'i-sun', 'i-leaf', 'i-moon']
const SOUND_VOLUME = 0.18

/* ---------- breathing ---------- */
export function createBreathing({ circle, label, button, t }) {
  let timer = null
  let inhale = true

  function step() {
    circle.classList.toggle('is-in', inhale)
    circle.classList.toggle('is-out', !inhale)
    label.textContent = inhale ? t().breatheIn : t().breatheOut
    const wait = inhale ? BREATH_IN_MS : BREATH_OUT_MS
    inhale = !inhale
    timer = window.setTimeout(step, wait)
  }

  function stop() {
    window.clearTimeout(timer)
    timer = null
    inhale = true
    circle.classList.remove('is-in', 'is-out')
    label.textContent = t().breatheReady
    button.textContent = t().breatheStart
  }

  button.addEventListener('click', () => {
    if (timer) { stop(); return }
    button.textContent = t().breatheStop
    step()
  })

  return { stop, refresh: () => { if (!timer) stop() } }
}

/* ---------- memory game ---------- */
function shuffled(items) {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

function iconSvg(id) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'ic')
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use')
  use.setAttribute('href', `#${id}`)
  svg.append(use)
  return svg
}

export function createMemory({ board, status, restart, t }) {
  let cards = []
  let open = []
  let moves = 0
  let locked = false

  function renderStatus() {
    const found = cards.filter((card) => card.found).length
    status.textContent = found === cards.length
      ? t().memoryWin.replace('{moves}', String(moves))
      : t().memoryMoves.replace('{moves}', String(moves))
  }

  function render() {
    board.replaceChildren(...cards.map((card, index) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.className = `memory-card${card.shown || card.found ? ' is-shown' : ''}${card.found ? ' is-found' : ''}`
      button.setAttribute('aria-label', card.shown || card.found ? t().memoryCardShown : t().memoryCardHidden)
      button.disabled = card.found
      const face = document.createElement('span')
      face.className = 'memory-face'
      face.append(iconSvg(card.icon))
      button.append(face)
      button.addEventListener('click', () => flip(index))
      return button
    }))
    renderStatus()
  }

  function flip(index) {
    const card = cards[index]
    if (locked || card.shown || card.found) return
    cards = cards.map((item, i) => (i === index ? { ...item, shown: true } : item))
    open = [...open, index]
    if (open.length === 2) {
      moves += 1
      const [a, b] = open
      if (cards[a].icon === cards[b].icon) {
        cards = cards.map((item, i) => (i === a || i === b ? { ...item, found: true, shown: false } : item))
        open = []
      } else {
        locked = true
        window.setTimeout(() => {
          cards = cards.map((item, i) => (i === a || i === b ? { ...item, shown: false } : item))
          open = []
          locked = false
          render()
        }, 900)
      }
    }
    render()
  }

  function reset() {
    cards = shuffled([...MEMORY_ICONS, ...MEMORY_ICONS]).map((icon) => ({ icon, shown: false, found: false }))
    open = []
    moves = 0
    locked = false
    render()
  }

  restart.addEventListener('click', reset)
  reset()
  return { refresh: render }
}

/* ---------- soothing sounds (generated, no audio file) ---------- */
function noiseBuffer(context, brown) {
  const length = context.sampleRate * 3
  const buffer = context.createBuffer(1, length, context.sampleRate)
  const data = buffer.getChannelData(0)
  let last = 0
  for (let i = 0; i < length; i += 1) {
    const white = Math.random() * 2 - 1
    if (brown) {
      last = (last + 0.02 * white) / 1.02
      data[i] = last * 3.5
    } else {
      data[i] = white
    }
  }
  return buffer
}

const SOUNDS = {
  rain: (context, out) => {
    const source = context.createBufferSource()
    source.buffer = noiseBuffer(context, false)
    source.loop = true
    const filter = context.createBiquadFilter()
    filter.type = 'highpass'
    filter.frequency.value = 900
    const soft = context.createBiquadFilter()
    soft.type = 'lowpass'
    soft.frequency.value = 6000
    source.connect(filter).connect(soft).connect(out)
    return [source]
  },
  waves: (context, out) => {
    const source = context.createBufferSource()
    source.buffer = noiseBuffer(context, true)
    source.loop = true
    const swell = context.createGain()
    swell.gain.value = 0.5
    const lfo = context.createOscillator()
    lfo.frequency.value = 0.09
    const depth = context.createGain()
    depth.gain.value = 0.45
    lfo.connect(depth).connect(swell.gain)
    source.connect(swell).connect(out)
    return [source, lfo]
  },
  calm: (context, out) => {
    const source = context.createBufferSource()
    source.buffer = noiseBuffer(context, true)
    source.loop = true
    const filter = context.createBiquadFilter()
    filter.type = 'lowpass'
    filter.frequency.value = 500
    source.connect(filter).connect(out)
    return [source]
  }
}

export function createSounds({ buttons, stopButton }) {
  let context = null
  let nodes = []
  let master = null
  let current = null

  function stop() {
    nodes.forEach((node) => { try { node.stop() } catch { /* already stopped */ } })
    nodes = []
    current = null
    buttons.forEach((button) => button.setAttribute('aria-pressed', 'false'))
    stopButton.hidden = true
  }

  function play(name) {
    if (current === name) { stop(); return }
    stop()
    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    if (!AudioContextClass) return
    context = context || new AudioContextClass()
    if (context.state === 'suspended') context.resume()
    master = context.createGain()
    master.gain.setValueAtTime(0, context.currentTime)
    master.gain.linearRampToValueAtTime(SOUND_VOLUME, context.currentTime + 1.5)
    master.connect(context.destination)
    nodes = SOUNDS[name](context, master)
    nodes.forEach((node) => node.start())
    current = name
    buttons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.sound === name)))
    stopButton.hidden = false
  }

  buttons.forEach((button) => button.addEventListener('click', () => play(button.dataset.sound)))
  stopButton.addEventListener('click', stop)
  return { stop }
}
