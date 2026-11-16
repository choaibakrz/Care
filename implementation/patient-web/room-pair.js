const form = document.querySelector('#pair-form')
const input = document.querySelector('#pairing-code')
const button = document.querySelector('#pair-submit')
const message = document.querySelector('#auth-message')

function showMessage(value) {
  message.textContent = value
  message.hidden = !value
  message.classList.remove('auth-success')
  message.setAttribute('role', 'alert')
}

async function postPairingCode(code) {
  let response
  try {
    response = await fetch('/api/room/pair', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ code })
    })
  } catch {
    throw new Error('Iris cannot be reached. Check the Wi-Fi connection and try again.')
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 429) throw new Error('Too many attempts. Wait a minute, then try again.')
    throw new Error(typeof payload.message === 'string' && payload.message ? payload.message : 'The tablet could not be connected. Ask the care team for a new code.')
  }
  return payload
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  showMessage('')
  const code = input.value.replace(/\s+/g, '').toUpperCase()
  if (!/^[A-Z0-9-]{8,32}$/.test(code)) {
    showMessage('Enter the room pairing code exactly as shown by the care team (8 to 32 letters and digits).')
    input.focus()
    return
  }
  button.disabled = true
  button.textContent = 'Connecting…'
  try {
    await postPairingCode(code)
    window.location.replace('./index.html')
  } catch (error) {
    showMessage(error instanceof Error ? error.message : 'The tablet could not be connected.')
    button.disabled = false
    button.innerHTML = 'Connect tablet <span aria-hidden="true">↗</span>'
    input.focus()
  }
})

// A link like login.html?code=AB12CD34EF56 (shown by the console) fills the code in.
const linkedCode = new URLSearchParams(window.location.search).get('code')
if (linkedCode) input.value = linkedCode.replace(/[^A-Za-z0-9-]/g, '').toUpperCase().slice(0, 32)

fetch('/api/room/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  .then((response) => { if (response.ok) window.location.replace('./index.html') })
  .catch(() => {})
