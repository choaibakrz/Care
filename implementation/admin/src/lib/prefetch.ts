/**
 * Downloads what the operator will need next, when the browser has nothing better to do.
 *
 * - On the login screen: the live map and the 3D scene (the biggest download), and in demo mode
 *   the demo clinic's first minutes, while the operator types.
 * - Once signed in: every other page, one after the other, so a click on the menu is instant.
 *
 * Nothing here changes what is shown; a failed prefetch is simply loaded again on use.
 */
import { config } from './config'

type IdleWindow = Window & { requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number }

const IDLE_TIMEOUT_MS = 2000

/** Runs `task` when the browser is idle (or after a short delay where idle callbacks do not exist). */
export function whenIdle(task: () => void): void {
  const idle = (window as IdleWindow).requestIdleCallback
  if (idle) idle(task, { timeout: IDLE_TIMEOUT_MS })
  else window.setTimeout(task, 200)
}

/** Runs the loaders one by one, each in its own idle moment, so they never fight the page. */
function oneByOne(loaders: Array<() => Promise<unknown>>): void {
  const next = (index: number): void => {
    if (index >= loaders.length) return
    whenIdle(() => { loaders[index]().catch(() => undefined).finally(() => next(index + 1)) })
  }
  next(0)
}

let beforeLogin = false
let afterLogin = false

export function prefetchBeforeLogin(): void {
  if (beforeLogin) return
  beforeLogin = true
  oneByOne([
    () => import('../pages/LiveMap'),
    () => import('../scene/ClinicScene'),
    // Demo only: the clinic plays its first minutes now, not after the click on "Open the console".
    ...(config.useMock ? [() => import('../mock/server').then((module) => module.warmUpDemo())] : []),
  ])
}

/**
 * Once signed in, the 3D map redraws every frame, so the browser is rarely idle: waiting for an
 * idle moment per page would take seconds each. One idle moment, then every page at once (each is
 * a few kilobytes).
 */
function allAtOnce(loaders: Array<() => Promise<unknown>>): void {
  whenIdle(() => { for (const load of loaders) load().catch(() => undefined) })
}

export function prefetchAfterLogin(): void {
  if (afterLogin) return
  afterLogin = true
  allAtOnce([
    () => import('../scene/ClinicScene'),
    () => import('../pages/Tasks'),
    () => import('../pages/Zones'),
    () => import('../pages/Stock'),
    () => import('../pages/Incidents'),
    () => import('../pages/Monitor'),
    () => import('../pages/Night'),
    () => import('../pages/Audit'),
    () => import('../pages/System'),
  ])
}
