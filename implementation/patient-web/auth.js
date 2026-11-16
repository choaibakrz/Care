const $ = (selector) => document.querySelector(selector)
const $$ = (selector) => [...document.querySelectorAll(selector)]

const state = { method: 'email', mode: 'signin', smsVisible: false, codeSent: false }
const OFFLINE_MESSAGE = 'Iris cannot be reached. Check the Wi-Fi connection and try again.'

function showMessage(message, kind = 'error') {
  const element = $('#auth-message')
  element.textContent = message
  element.hidden = !message
  element.classList.toggle('auth-success', kind === 'success')
  element.setAttribute('role', kind === 'success' ? 'status' : 'alert')
}

function setBusy(button, busy, label) {
  button.disabled = busy
  if (busy) button.dataset.previousLabel = button.textContent
  button.textContent = busy ? 'Please wait…' : label || button.dataset.previousLabel
}

/* ---------- account or room tablet ---------- */
function showConnection(kind) {
  const tablet = kind === 'tablet'
  $('#account-panel').hidden = tablet
  $('#tablet-panel').hidden = !tablet
  $$('[data-connect]').forEach((tab) => {
    const active = tab.dataset.connect === kind
    tab.classList.toggle('is-active', active)
    tab.setAttribute('aria-selected', String(active))
  })
  document.title = tablet ? 'Connect tablet · Care' : `${state.mode === 'signup' ? 'Create account' : 'Sign in'} · Care`
  showMessage('')
}

function updateMethod(method) {
  state.method = method
  const phone = method === 'phone'
  const identifier = $('#identifier')
  $('#identifier-label').textContent = phone ? 'Phone number' : 'Email address'
  identifier.type = phone ? 'tel' : 'email'
  identifier.inputMode = phone ? 'tel' : 'email'
  identifier.autocomplete = phone ? 'tel' : 'username'
  identifier.placeholder = phone ? '+41 79 123 45 67' : 'you@example.com'
  identifier.value = ''
  $$('.auth-tab').forEach((tab) => {
    const active = tab.dataset.authMethod === method
    tab.classList.toggle('is-active', active)
    tab.setAttribute('aria-selected', String(active))
  })
  if (!phone && state.smsVisible) showPasswordForm()
  updateSmsEntry()
  showMessage('')
}

/** The SMS option only exists for phone sign-in (an SMS code also creates the account). */
function updateSmsEntry() {
  const offerSms = state.method === 'phone' && !state.smsVisible
  $('#show-sms').hidden = !offerSms
  $('.auth-divider').hidden = !offerSms
}

function updateMode(mode) {
  state.mode = mode
  const signup = mode === 'signup'
  $('#auth-eyebrow').textContent = signup ? 'CREATE YOUR ACCESS' : 'WELCOME BACK'
  $('#auth-title').textContent = signup ? 'Create account' : 'Sign in'
  $('#auth-subtitle').textContent = signup ? 'Set up your patient access with your email or phone.' : 'Use the contact method connected to your patient account.'
  $('#confirm-password-field').hidden = !signup
  $('#confirm-password').required = signup
  $('#password').autocomplete = signup ? 'new-password' : 'current-password'
  $('#password-submit').innerHTML = signup ? 'Create account <span aria-hidden="true">↗</span>' : 'Sign in <span aria-hidden="true">↗</span>'
  $('#toggle-auth-mode').textContent = signup ? 'Already have an account? Sign in' : 'Need an account? Create one'
  document.title = `${signup ? 'Create account' : 'Sign in'} · Care`
}

function showPasswordForm() {
  state.smsVisible = false
  $('#password-form').hidden = false
  $('#sms-form').hidden = true
  updateSmsEntry()
}

/* ---------- requests ---------- */
async function postJson(url, body) {
  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body)
    })
  } catch {
    throw new Error(OFFLINE_MESSAGE)
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 429) throw new Error('Too many attempts. Wait a minute, then try again.')
    throw new Error(typeof payload.message === 'string' && payload.message ? payload.message : 'Sign-in could not be completed. Please try again.')
  }
  return payload
}

function requireFirstName() {
  const firstName = $('#first-name').value.trim()
  if (!firstName) {
    showMessage('Enter your first name, so we know how to welcome you.')
    $('#first-name').focus()
  }
  return firstName
}

async function signIn(event) {
  event.preventDefault()
  showMessage('')
  const firstName = requireFirstName()
  if (!firstName) return
  if ($('#password').value.length < 8) {
    showMessage('The password needs at least 8 characters.')
    $('#password').focus()
    return
  }
  if (state.mode === 'signup' && $('#password').value !== $('#confirm-password').value) {
    showMessage('The passwords do not match.')
    return
  }
  const button = $('#password-submit')
  const label = state.mode === 'signup' ? 'Create account ↗' : 'Sign in ↗'
  setBusy(button, true)
  try {
    const endpoint = state.mode === 'signup' ? '/api/auth/signup' : '/api/auth/login'
    const payload = await postJson(endpoint, { identifier: $('#identifier').value.trim(), password: $('#password').value, first_name: firstName })
    if (payload.needsConfirmation) {
      showMessage(payload.message || 'Check your inbox to confirm the account, then sign in.', 'success')
      setBusy(button, false, label)
      return
    }
    window.location.replace('./index.html')
  } catch (error) {
    showMessage(error.message)
    setBusy(button, false, label)
  }
}

async function requestCode(event) {
  event.preventDefault()
  showMessage('')
  if (!requireFirstName()) return
  if (!$('#sms-phone').value.trim()) {
    showMessage('Enter your phone number, for example +41 79 123 45 67.')
    $('#sms-phone').focus()
    return
  }
  const button = $('#send-code')
  setBusy(button, true)
  try {
    await postJson('/api/auth/request-otp', { phone: $('#sms-phone').value.trim() })
    state.codeSent = true
    $('#code-step').hidden = false
    $('#sms-code').focus()
    setBusy(button, false, 'Send code again')
    showMessage('A six-digit code is on its way by SMS. It is valid for 10 minutes.', 'success')
  } catch (error) {
    showMessage(error.message)
    setBusy(button, false, 'Send me a code')
  }
}

async function verifyCode() {
  showMessage('')
  const firstName = requireFirstName()
  if (!firstName) return
  const code = $('#sms-code').value.trim()
  if (!/^\d{6}$/.test(code)) {
    showMessage('Enter the six digits from the SMS.')
    $('#sms-code').focus()
    return
  }
  const button = $('#verify-code')
  setBusy(button, true)
  try {
    await postJson('/api/auth/verify-otp', { phone: $('#sms-phone').value.trim(), token: code, first_name: firstName })
    window.location.replace('./index.html')
  } catch (error) {
    showMessage(error.message)
    setBusy(button, false, 'Verify code ↗')
  }
}

/* ---------- events ---------- */
$$('[data-connect]').forEach((button) => button.addEventListener('click', () => showConnection(button.dataset.connect)))
$$('[data-auth-method]').forEach((button) => button.addEventListener('click', () => updateMethod(button.dataset.authMethod)))
$('#password-form').addEventListener('submit', signIn)
$('#show-sms').addEventListener('click', () => {
  state.smsVisible = true
  $('#password-form').hidden = true
  $('#sms-form').hidden = false
  updateSmsEntry()
  $('#sms-phone').value = $('#identifier').value
  $('#sms-phone').focus()
  showMessage('')
})
$('#back-to-password').addEventListener('click', () => { showPasswordForm(); showMessage('') })
$('#sms-form').addEventListener('submit', requestCode)
$('#verify-code').addEventListener('click', verifyCode)
$('#sms-code').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); void verifyCode() }
})
$('#toggle-auth-mode').addEventListener('click', () => {
  showPasswordForm()
  updateMode(state.mode === 'signin' ? 'signup' : 'signin')
  $('#password').value = ''
  $('#confirm-password').value = ''
  showMessage('')
})

updateMethod('email')
updateMode('signin')
const params = new URLSearchParams(window.location.search)
if (params.has('code') || window.location.hash === '#tablet') showConnection('tablet')

fetch('/api/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  .then((response) => { if (response.ok) window.location.replace('./index.html') })
  .catch(() => {
    // No server reachable: the forms stay usable and explain the problem on submit.
  })
