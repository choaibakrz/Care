/**
 * The static login screen of `index.html` shows before any script runs. When the panel starts,
 * it takes over what was typed there (and whether Enter was already pressed) so nothing is lost.
 * The values stay in this module's memory until the login screen has used them, then are forgotten.
 */
export interface BootLogin {
  username: string
  password: string
  /** Enter was pressed before the panel was ready. */
  submitted: boolean
  /** Which field had the focus. */
  focus: 'username' | 'password' | null
}

let captured: BootLogin | null = null

/** Reads the static form. Must run before React replaces it. */
export function captureBootLogin(): void {
  const form = document.getElementById('boot-form')
  if (!form) return
  const username = (document.getElementById('boot-username') as HTMLInputElement | null)?.value ?? ''
  const password = (document.getElementById('boot-password') as HTMLInputElement | null)?.value ?? ''
  const active = document.activeElement?.id
  captured = { username, password, submitted: form.dataset.submitted === 'true', focus: active === 'boot-username' ? 'username' : active === 'boot-password' ? 'password' : null }
}

/** What the static form held. The same answer until `forgetBootLogin` (React may ask twice). */
export function peekBootLogin(): BootLogin | null {
  // Read again while the static form is still on screen (React renders before it replaces it):
  // what was typed after `captureBootLogin` ran (the bundle loads in between) is kept too.
  if (document.getElementById('boot-form')) captureBootLogin()
  return captured
}

/** Drops the typed values (the password among them) once the login screen has them. */
export function forgetBootLogin(): void {
  captured = null
}
