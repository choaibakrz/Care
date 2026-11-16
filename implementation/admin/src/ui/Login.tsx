import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, KeyRound, Lock, ShieldCheck, WifiOff } from 'lucide-react'
import { backend } from '../lib/backend'
import { config } from '../lib/config'
import { errorMessage } from '../lib/format'
import { useStore } from '../state/store'
import { forgetBootLogin, peekBootLogin } from './boot'
import { Logo } from './Logo'

export function Login() {
  const signIn = useStore((state) => state.signIn)
  // What was typed in the static login screen (index.html) before the panel started, read once.
  const [boot] = useState(peekBootLogin)
  const bootHandled = useRef(false)
  const authTokenHandled = useRef(false)
  const [username, setUsername] = useState(boot?.username || (config.useMock ? 'admin' : ''))
  const [password, setPassword] = useState(boot?.password || (config.useMock ? 'demo' : ''))
  const usernameField = useRef<HTMLInputElement>(null)
  const passwordField = useRef<HTMLInputElement>(null)
  const form = useRef<HTMLFormElement>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  // "I have an enrolment code": a new account from a one-time code (docs/accounts.md).
  const [enrolling, setEnrolling] = useState(false)
  const [code, setCode] = useState('')
  const [pseudonym, setPseudonym] = useState('')
  const [notice, setNotice] = useState('')

  const enrol = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const operator = await backend.enrol({ code, username, password, pseudonym })
      setNotice(`Account created: ${operator}. Signing in…`)
      signIn(await backend.login(username, password))
    } catch (reason) {
      setError(errorMessage(reason))
      setBusy(false)
    }
  }

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      signIn(await backend.login(username, password))
    } catch (reason) {
      setError(errorMessage(reason))
      setBusy(false)
    }
  }

  useEffect(() => {
    forgetBootLogin()
    if (bootHandled.current) return
    bootHandled.current = true
    if (boot?.focus === 'username') usernameField.current?.focus()
    if (boot?.focus === 'password') passwordField.current?.focus()
    // Enter was pressed on the static screen: sign in now that the panel can.
    if (boot?.submitted) form.current?.requestSubmit()
  }, [boot])

  useEffect(() => {
    if (authTokenHandled.current) return
    const hash = window.location.hash.slice(1)
    if (!hash) return
    const params = new URLSearchParams(hash)
    const accessToken = params.get('access_token')
    const authError = params.get('error_description') || params.get('error')
    if (!accessToken && !authError) return
    authTokenHandled.current = true
    window.history.replaceState(null, document.title, `${window.location.pathname}${window.location.search}`)
    if (authError) {
      setError('This sign-in link is expired or invalid. Request a new one.')
      return
    }
    if (!accessToken) return
    setBusy(true)
    setError('')
    void backend.loginWithToken(accessToken).then((session) => {
      signIn(session)
    }).catch(() => {
      setError('This sign-in link is expired or not authorized for the admin console.')
      setBusy(false)
    })
  }, [signIn])

  return (
    <main className="login">
      <section className="login-card">
        <Logo />
        <div className="login-copy">
          <p className="eyebrow">Admin console · local network</p>
          <h1>Watch the robots.<br /><span>Stop them in one click.</span></h1>
          <p>Live 3D map of the clinic, zones, stock and the night round. The panel asks; every robot decides for itself and says why when it refuses.</p>
        </div>
        {enrolling ? (
          <form className="login-form" onSubmit={(event) => { void enrol(event) }}>
            <label className="field">Enrolment code<input className="input mono" value={code} onChange={(event) => setCode(event.target.value)} placeholder="XXXX-XXXX-XXXX" autoComplete="one-time-code" required /></label>
            <label className="field">Choose a username<input className="input" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
            <label className="field">Choose a password<input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label>
            <label className="field">Pseudonym (shown to others, never your real name)<input className="input" value={pseudonym} onChange={(event) => setPseudonym(event.target.value)} maxLength={32} placeholder="Admin 1" required /></label>
            <p className="login-hint">Your username and password never leave this computer: the console derives a key from them and sends only the key. They cannot be recovered, so remember them.</p>
            {notice && <p className="login-hint" role="status">{notice}</p>}
            {error && <p className="login-error" role="alert">{error}</p>}
            <button className="button is-primary is-wide login-submit" type="submit" disabled={busy}>{busy ? 'Creating the account…' : <>Create my account <ArrowRight size={16} /></>}</button>
            <button className="button is-wide" type="button" disabled={busy} onClick={() => { setEnrolling(false); setError('') }}>Back to sign in</button>
          </form>
        ) : (
          <form ref={form} className="login-form" onSubmit={(event) => { void submit(event) }}>
            <label className="field">Administrator username or email<input ref={usernameField} className="input" type="text" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
            <label className="field">Password<input ref={passwordField} className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
            {error && <p className="login-error" role="alert">{error}</p>}
            <button className="button is-primary is-wide login-submit" type="submit" disabled={busy}>{busy ? 'Signing in…' : <>Open the console <ArrowRight size={16} /></>}</button>
            <button className="button is-wide login-enrol" type="button" disabled={busy} onClick={() => { setEnrolling(true); setError(''); setPassword('') }}><KeyRound size={15} /> I have an enrolment code</button>
          </form>
        )}
        <ul className="login-facts">
          <li><ShieldCheck size={15} />Admin role only. The token stays in memory, never in the address bar.</li>
          <li><WifiOff size={15} />Runs without Internet: fonts, map and code are all on this computer.</li>
          {config.useMock && <li className="is-demo"><Lock size={15} />Demo mode: any non-empty name and password. All data is invented.</li>}
        </ul>
      </section>
      <aside className="login-art" aria-hidden="true">
        <div className="login-plan">
          {Array.from({ length: 9 }, (_, index) => <span key={index} className={`room room-${index}`} />)}
          <i className="bot bot-a" />
          <i className="bot bot-b" />
          <i className="bot bot-c" />
          <svg viewBox="0 0 600 360" preserveAspectRatio="none"><path d="M70 290 C 160 290, 180 170, 300 170 S 470 90, 540 70" /></svg>
        </div>
        <p className="login-caption"><b className="mono">4</b> robots · <b className="mono">2</b> floors · invented clinic</p>
      </aside>
    </main>
  )
}
