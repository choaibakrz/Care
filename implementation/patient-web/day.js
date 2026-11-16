/* "My day": today's programme, the home "next up" card and the questions for the doctor. */
import { addQuestion, exampleDayProgram, getDayProgram, listQuestions, removeQuestion } from './patient-api.js'

const PROGRAM_ICONS = {
  breakfast: { icon: 'i-meal', tone: 'tone-sun' },
  round: { icon: 'i-stethoscope', tone: 'tone-teal' },
  physio: { icon: 'i-physio', tone: 'tone-sage' },
  lunch: { icon: 'i-meal', tone: 'tone-sun' },
  visits: { icon: 'i-users', tone: 'tone-rose' },
  dinner: { icon: 'i-meal', tone: 'tone-sun' }
}

const $ = (selector) => document.querySelector(selector)

function minutes(time) {
  const [hours, mins] = time.split(':').map(Number)
  return hours * 60 + mins
}

function nowMinutes() {
  const now = new Date()
  return now.getHours() * 60 + now.getMinutes()
}

function icon(id) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'ic')
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use')
  use.setAttribute('href', `#${id}`)
  svg.append(use)
  return svg
}

/** An item is "now" from its start until its end (or 45 minutes when it has none). */
function phaseOf(item, now) {
  const start = minutes(item.time)
  const end = item.until ? minutes(item.until) : start + 45
  if (now >= end) return 'past'
  if (now >= start) return 'now'
  return 'next'
}

export function createDay({ t, notify, language, hasPatient }) {
  let program = { items: [], demo: true }
  let questions = []
  let patient = true

  function renderProgram() {
    const now = nowMinutes()
    $('#program-demo').hidden = !program.demo
    $('#program-list').replaceChildren(...program.items.map((item) => {
      const meta = PROGRAM_ICONS[item.kind]
      const phase = phaseOf(item, now)
      const row = document.createElement('li')
      row.className = `program-item is-${phase}`
      const time = document.createElement('span')
      time.className = 'program-time'
      time.textContent = item.time
      const badge = document.createElement('span')
      badge.className = `request-icon ${meta.tone}`
      badge.append(icon(meta.icon))
      const text = document.createElement('span')
      text.className = 'program-text'
      const title = document.createElement('strong')
      title.textContent = t().prog[item.kind]
      text.append(title)
      if (item.until || phase === 'now') {
        const detail = document.createElement('small')
        detail.textContent = [phase === 'now' ? t().programNow : '', item.until ? t().programUntil.replace('{time}', item.until) : ''].filter(Boolean).join(' · ')
        text.append(detail)
      }
      row.append(time, badge, text)
      return row
    }))
    renderNextUp(now)
  }

  function renderNextUp(now) {
    const next = program.items.find((item) => minutes(item.time) > now)
    const card = $('#next-up')
    card.hidden = !next
    if (!next) return
    const meta = PROGRAM_ICONS[next.kind]
    const badge = $('#next-up-icon')
    badge.className = `info-icon ${meta.tone}`
    badge.replaceChildren(icon(meta.icon))
    $('#next-up-label').textContent = t().nextUpLabel.replace('{time}', next.time)
    $('#next-up-title').textContent = t().prog[next.kind]
  }

  function renderQuestions() {
    $('#questions-count').textContent = String(questions.length)
    $('#question-empty').hidden = questions.length > 0
    $('#question-list').replaceChildren(...questions.map((question) => {
      const row = document.createElement('li')
      row.className = 'question-item'
      const text = document.createElement('p')
      text.textContent = question.text
      const time = document.createElement('small')
      time.textContent = new Intl.DateTimeFormat(language(), { hour: '2-digit', minute: '2-digit' }).format(question.createdAt)
      const body = document.createElement('div')
      body.append(text, time)
      const remove = document.createElement('button')
      remove.type = 'button'
      remove.className = 'icon-button'
      remove.setAttribute('aria-label', t().questionsRemove)
      remove.title = t().questionsRemove
      remove.append(icon('i-trash'))
      remove.addEventListener('click', async () => {
        remove.disabled = true
        try {
          await removeQuestion(question.id)
          questions = questions.filter((item) => item.id !== question.id)
          renderQuestions()
        } catch {
          remove.disabled = false
          notify(t().questionsError)
        }
      })
      row.append(body, remove)
      return row
    }))
  }

  $('#question-form').addEventListener('submit', async (event) => {
    event.preventDefault()
    const input = $('#question-input')
    const text = input.value.trim()
    if (!text) { input.focus(); return }
    if (!patient) { notify('No patient is assigned to this room yet. Ask the care team.'); return }
    const button = event.currentTarget.querySelector('button[type="submit"]')
    button.disabled = true
    try {
      const question = await addQuestion(text)
      questions = [...questions, question]
      input.value = ''
      renderQuestions()
      notify(t().questionsSaved)
    } catch {
      notify(t().questionsError)
    } finally {
      button.disabled = false
    }
  })

  async function load() {
    patient = await (hasPatient || Promise.resolve(true))
    if (!patient) {
      program = exampleDayProgram()
      questions = []
      refresh()
      return
    }
    try { program = await getDayProgram() } catch { program = exampleDayProgram() }
    try { questions = await listQuestions() } catch { questions = [] }
    refresh()
  }

  function refresh() {
    renderProgram()
    renderQuestions()
  }

  load()
  window.setInterval(renderProgram, 60000)
  return { refresh }
}
