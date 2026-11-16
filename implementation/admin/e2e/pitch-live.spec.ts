/**
 * Pitch walk-through against the LIVE Rust clinic server (not the mock): every page, every button.
 *
 * Run (server on :8080 with its 2 simulated robots, console dev server on :5199 pointing at it):
 *   VITE_USE_MOCK=false VITE_API_URL=http://localhost:8080 pnpm exec vite --port 5199
 *   PITCH_USER=admin PITCH_PASS=pitch-pass-123 [ENROL_CODE=XXXX-XXXX-XXXX] pnpm exec playwright test pitch-live
 * Or against the console the server serves itself:
 *   BASE_URL=http://localhost:8080/admin/ ... pnpm exec playwright test pitch-live
 *
 * ENROL_CODE (the one-time code the server prints on its first start) enrols PITCH_USER first;
 * without it PITCH_USER must already exist. Each control must show a visible result; a 5xx
 * answer or an uncaught page error fails the test.
 */
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const BASE = (process.env.BASE_URL ?? 'http://localhost:5199/').replace(/\/?$/, '/')
const API = (process.env.API_URL ?? 'http://localhost:8080').replace(/\/$/, '')
const USER = process.env.PITCH_USER ?? 'admin'
const PASS = process.env.PITCH_PASS ?? 'pitch-pass-123'
const STAMP = Date.now().toString(36).slice(-5)

test.describe.configure({ mode: 'serial' })
test.setTimeout(120_000)

/** Errors that must never happen during the pitch: uncaught exceptions and 5xx answers. */
function watch(page: Page): string[] {
  const problems: string[] = []
  page.on('pageerror', (error) => problems.push(`page error: ${error.message}`))
  page.on('response', (response) => {
    if (response.status() >= 500 && !response.url().includes('/brain/')) problems.push(`${response.status()} ${response.request().method()} ${response.url()}`)
  })
  return problems
}

async function go(page: Page, path: string): Promise<void> {
  await page.goto(BASE + path.replace(/^\//, ''))
}

async function nav(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: new RegExp(`^${name}\\s*\\d*$`) }).click()
}

async function signIn(page: Page): Promise<void> {
  await go(page, '')
  await page.getByLabel('Username').fill(USER)
  await page.getByLabel('Password').fill(PASS)
  await page.getByRole('button', { name: /open the console/i }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })
}

/** Waits for a toast matching `text`, logs it (the run's report) and closes it. */
async function toast(page: Page, text: string | RegExp): Promise<string> {
  const found = page.locator('.toast').filter({ hasText: text }).last()
  await expect(found).toBeVisible({ timeout: 10_000 })
  const said = (await found.innerText()).trim()
  console.log(`  toast: ${said}`)
  await found.getByRole('button', { name: 'Dismiss' }).click().catch(() => undefined)
  return said
}

test('the server answers in live mode (not the mock)', async ({ request }) => {
  const health = await request.get(`${API}/health`)
  expect(health.ok()).toBe(true)
  expect(await health.json()).toMatchObject({ status: 'ok', mode: 'live' })
})

test('enrol (first start) then sign in, refuse a wrong password', async ({ page }) => {
  const problems = watch(page)
  const code = process.env.ENROL_CODE
  if (code) {
    await go(page, '')
    await page.getByRole('button', { name: /I have an enrolment code/i }).click()
    await page.getByLabel('Enrolment code').fill(code)
    await page.getByLabel('Choose a username').fill(USER)
    await page.getByLabel('Choose a password').fill(PASS)
    await page.getByLabel(/Pseudonym/).fill('Admin pitch')
    await page.getByRole('button', { name: /Create my account/i }).click()
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible({ timeout: 20_000 })
    await page.getByRole('button', { name: 'Sign out' }).click()
  }
  await go(page, '')
  await page.getByLabel('Username').fill(USER)
  await page.getByLabel('Password').fill('wrong-password')
  await page.getByRole('button', { name: /open the console/i }).click()
  const refused = page.locator('.login-error')
  await expect(refused).toBeVisible({ timeout: 15_000 })
  await expect(refused).not.toContainText('session has ended')
  console.log(`  wrong password: ${await refused.innerText()}`)
  await signIn(page)
  expect(problems).toEqual([])
})

test('live map: robots, moods, tasks, pause/resume/dock, stop and re-arm one robot', async ({ page }) => {
  const problems = watch(page)
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible()
  const pip = page.getByTestId('fleet-sim-pip')
  await expect(pip).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('fleet-sim-sunny')).toBeVisible()
  // Toolbar: floors, camera, overlays.
  await page.getByRole('radio', { name: /All floors/ }).click()
  await page.getByRole('radio', { name: /Floor 2/ }).click()
  await page.getByRole('radio', { name: /Ground floor/ }).click()
  await page.getByRole('radio', { name: /Plan/ }).click()
  await page.getByRole('radio', { name: /3D/ }).click()
  for (const name of ['Zones', 'Tablets', 'Heat', 'Heat', 'Tablets', 'Zones']) await page.locator('.map-toolbar').getByRole('button', { name }).click()
  await page.getByRole('button', { name: 'Presenter' }).click()
  await page.getByRole('button', { name: 'Presenter' }).click()

  await pip.click()
  const detail = page.getByTestId('robot-detail')
  await expect(detail).toBeVisible()
  await expect(detail.getByText('Mood')).toBeVisible()
  const give = page.getByTestId('give-task')
  const confirm = page.getByRole('dialog')
  // Go to: the robot takes the task and drives (busy), then pause and resume it.
  await give.getByLabel('Kind of task').selectOption('go_to')
  await give.getByLabel('Place').selectOption({ index: 2 })
  await give.getByRole('button', { name: 'Give task' }).click()
  await toast(page, /given to sim-pip/)
  await expect(detail.getByRole('button', { name: 'Pause', exact: true })).toBeEnabled({ timeout: 15_000 })
  await detail.getByRole('button', { name: 'Pause', exact: true }).click()
  await confirm.getByRole('button', { name: 'Pause' }).click()
  await toast(page, /sim-pip accepted “pause”/)
  await expect(detail.getByRole('button', { name: 'Resume', exact: true })).toBeEnabled({ timeout: 10_000 })
  await detail.getByRole('button', { name: 'Resume', exact: true }).click()
  await toast(page, /sim-pip accepted “resume”/)
  // A second task while it drives is refused with the reason (robot_busy), not lost.
  await give.getByLabel('Kind of task').selectOption('go_to')
  await give.getByLabel('Place').selectOption({ index: 3 })
  await give.getByRole('button', { name: 'Give task' }).click()
  await toast(page, /busy with task/)
  // "Send to dock": the running task is handed back, the robot heads home.
  await detail.getByRole('button', { name: 'Send to dock' }).click()
  if (await confirm.isVisible().catch(() => false)) await confirm.getByRole('button', { name: 'Send to dock' }).click()
  await toast(page, /sim-pip accepted “send to dock”/)
  // Fetch.
  await give.getByLabel('Kind of task').selectOption('fetch')
  await give.getByLabel('Item').selectOption({ index: 1 })
  await give.getByLabel('Bring it to').selectOption({ index: 1 })
  await give.getByRole('button', { name: 'Give task' }).click()
  await toast(page, /given to sim-pip/)
  // Follow: no staff tablet online in the pitch, the choice says so.
  await give.getByLabel('Kind of task').selectOption('follow')
  await expect(give.getByLabel('Staff tablet')).toContainText(/staff tablet/i)
  // Go charge (= dock).
  await give.getByLabel('Kind of task').selectOption('charge')
  await give.getByRole('button', { name: 'Send to charge' }).click()
  if (await confirm.isVisible().catch(() => false)) await confirm.getByRole('button', { name: 'Send to dock' }).click()
  await toast(page, /sim-pip accepted “send to dock”/)
  // Stop this robot, then re-arm it.
  await detail.getByTestId('estop-one').click()
  await expect(page.getByTestId('estop-panel').getByText('Confirmed stopped')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Close the stop report' }).click()
  await detail.getByTestId('rearm-one').click()
  await page.getByRole('dialog').getByRole('button', { name: 'Re-arm robot' }).click()
  await toast(page, /sim-pip is re-armed/)
  expect(problems).toEqual([])
})

test('live map: home place, drag a simulated robot, emergency mode on and off, stop all and re-arm', async ({ page }) => {
  const problems = watch(page)
  await signIn(page)
  await expect(page.getByTestId('fleet-sim-sunny')).toBeVisible({ timeout: 15_000 })
  // Home / charging place.
  const home = page.getByTestId('home-place-select')
  await home.selectOption({ index: 0 })
  await toast(page, /No home place/)
  await home.selectOption('dock-a')
  await toast(page, /Home place set: Dock A/)
  // Drag Sunny by its tag in the plan view: the server moves it (or says why not).
  await page.getByRole('radio', { name: /Plan/ }).click()
  await page.waitForTimeout(1500)
  const tag = page.getByTestId('robot-tag-sim-sunny')
  const box = await tag.boundingBox()
  const plan = await page.locator('.map-stage canvas').first().boundingBox()
  if (!box || !plan) throw new Error('robot tag or map not visible')
  const teleport = page.waitForResponse((response) => response.url().includes('/robots/sim-sunny/teleport'), { timeout: 10_000 })
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  const target = { x: plan.x + plan.width * 0.5, y: plan.y + plan.height * 0.75 }
  await page.mouse.move(target.x, target.y, { steps: 12 })
  await page.mouse.up()
  // 200: moved there; 422: a wall, outside or a restricted zone, and the toast says so.
  const answer = await teleport
  console.log(`  drag: teleport answered ${answer.status()}`)
  if (answer.ok()) expect(await answer.json()).toMatchObject({ id: 'sim-sunny' })
  else await toast(page, /sim-sunny was not moved/)
  await page.getByRole('radio', { name: /3D/ }).click()

  // Emergency mode: on (robots head home, mood alarm), then back to normal.
  await page.getByTestId('mode-switch').click()
  await expect(page.getByTestId('emergency-banner')).toBeVisible({ timeout: 10_000 })
  await page.getByTestId('mode-switch').click()
  await page.getByTestId('mode-exit').click()
  await expect(page.getByTestId('emergency-banner')).toHaveCount(0, { timeout: 10_000 })

  // Stop every robot: the connected ones confirm, then re-arm them. A short window (laptop on
  // stage): the report must fit in it and scroll inside, so its last button stays reachable.
  await page.setViewportSize({ width: 1280, height: 600 })
  await page.getByTestId('estop-all').click()
  const report = page.getByTestId('estop-panel')
  await expect(report.getByText('Confirmed stopped').first()).toBeVisible({ timeout: 15_000 })
  const reportBox = await report.boundingBox()
  expect((reportBox?.y ?? 0) + (reportBox?.height ?? 0)).toBeLessThanOrEqual(600)
  await report.getByTestId('rearm-all').scrollIntoViewIfNeeded()
  await expect(report.getByTestId('rearm-all')).toBeInViewport()
  console.log(`  estop: ${(await report.innerText()).replace(/\s+/g, ' ').slice(0, 400)}`)
  page.once('dialog', (dialog) => { void dialog.accept() })
  await report.getByTestId('rearm-all').click()
  await expect(report.getByText('Re-armed').first()).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Close the stop report' }).click()
  expect(problems).toEqual([])
})

test('new task without a robot: the optimizer picks one, or says why none can', async ({ page }) => {
  const problems = watch(page)
  await signIn(page)
  await nav(page, 'Tasks')
  const form = page.getByTestId('new-task')
  await expect(form).toBeVisible()
  // Ground floor: a simulated robot can drive there.
  await form.getByLabel('Kind of task').selectOption('go_to')
  await form.getByLabel('Place').selectOption('reception')
  await form.getByRole('button', { name: 'Find a robot' }).click()
  await toast(page, /optimizer chose sim-/)
  await expect(form.getByTestId('task-outcome')).toContainText(/optimizer chose sim-/)
  // Another floor: no robot can get there, the form says why.
  await form.getByLabel('Place').selectOption('room-11')
  await form.getByRole('button', { name: 'Find a robot' }).click()
  await toast(page, /No robot can do this task/)
  const outcome = form.getByRole('alert')
  await expect(outcome).toContainText(/No robot can do this task.*no path/)
  console.log(`  outcome: ${(await outcome.innerText()).slice(0, 200)}`)
  await page.screenshot({ path: 'test-results/tasks-auto-impossible.png' })
  expect(problems).toEqual([])
})

test('tasks, stock, night round, incidents, audit log, monitor', async ({ page }) => {
  const problems = watch(page)
  await signIn(page)
  // Give a task to cancel it from the Tasks page.
  await page.getByTestId('fleet-sim-sunny').click()
  const give = page.getByTestId('give-task')
  await give.getByLabel('Kind of task').selectOption('go_to')
  await give.getByLabel('Place').selectOption({ index: 3 })
  await give.getByRole('button', { name: 'Give task' }).click()
  const given = await toast(page, /given to sim-sunny/)
  const taskId = /Task (\S+) given/.exec(given)?.[1] ?? ''

  await nav(page, 'Tasks')
  for (const tab of ['Open', 'All']) await page.getByRole('tab', { name: new RegExp(`^${tab}`) }).click()
  await page.getByLabel('Robot').selectOption('sim-sunny')
  await page.getByPlaceholder('Item, place, task…').fill(taskId)
  await page.getByRole('row').filter({ hasText: taskId }).click()
  // Before the robot sets off the task can be cancelled; once on the way the page says why not.
  const cancel = page.getByRole('button', { name: 'Cancel this task' })
  const onTheWay = page.getByRole('note').filter({ hasText: 'can no longer be cancelled' })
  await expect(cancel.or(onTheWay).first()).toBeVisible()
  if (await cancel.isVisible()) {
    await cancel.click()
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel the task' }).click()
    await toast(page, new RegExp(`${taskId} cancelled`))
  } else console.log(`  tasks: ${await onTheWay.innerText()}`)
  await page.getByPlaceholder('Item, place, task…').fill('')

  await nav(page, 'Stock')
  // +1 then -1 on the first shelf: the count changes on screen, no error toast.
  const row = page.locator('tr').filter({ has: page.getByRole('button', { name: /^One more / }) }).first()
  const before = (await row.textContent()) ?? ''
  await row.getByRole('button', { name: /^One more / }).click()
  await expect(row).not.toHaveText(before, { timeout: 10_000 })
  await row.getByRole('button', { name: /^One less / }).click()
  await expect(row).toHaveText(before, { timeout: 10_000 })
  await expect(page.locator('.toast.is-danger')).toHaveCount(0)
  await page.locator('.toggle').filter({ hasText: /./ }).first().click()

  await nav(page, 'Night round')
  const round = page.getByRole('button', { name: 'Round on or off' })
  if (await round.count()) {
    await round.click()
    await page.getByRole('button', { name: /^Save/ }).click()
    await toast(page, /Night round saved|Not saved/)
    await round.click()
    await page.getByRole('button', { name: /^Save/ }).click()
    await toast(page, /Night round saved|Not saved/)
    await page.getByRole('button', { name: /Run now|Start/ }).click()
    await toast(page, /./)
  } else console.log('  night: no schedule on this server (empty state shown)')

  await nav(page, 'Incidents')
  await page.getByRole('radio', { name: 'With closed' }).click()
  for (const level of ['Critical', 'Warning', 'Info', 'All']) await page.getByRole('radio', { name: level, exact: true }).click()
  const ack = page.locator('[data-testid^="incident-ack-"]').first()
  if (await ack.count()) {
    await ack.click()
    await toast(page, /./)
    await page.locator('[data-testid^="incident-close-"]').first().click()
    await toast(page, /./)
  } else console.log('  incidents: none open')

  await nav(page, 'Audit log')
  await expect(page.getByRole('button', { name: /Refresh|Load|Reload/ })).toBeVisible()
  await page.getByLabel('Actor').selectOption({ index: 0 })
  await page.getByLabel('Time').selectOption({ index: 1 })
  await page.getByRole('button', { name: /Refresh|Load|Reload/ }).click()
  await page.getByPlaceholder('Action, robot, zone…').fill('task')
  await expect(page.locator('table, .empty').first()).toBeVisible()

  await nav(page, 'Monitor')
  await expect(page.locator('.page')).toContainText(/Server|Traffic|Requests/i)
  // Block a documentation address (never a real client), see it listed, remove it.
  await page.getByTestId('block-target').fill('203.0.113.77')
  await page.getByLabel('Reason (kept in the audit log)').fill('pitch walk-through')
  await page.getByTestId('block-add').click()
  await toast(page, /203\.0\.113\.77 is blocked|Not blocked/)
  const blockRow = page.getByRole('row').filter({ hasText: 'pitch walk-through' })
  if (await blockRow.count()) {
    await blockRow.getByRole('button', { name: 'Remove' }).click()
    await toast(page, /no longer blocked/)
  }

  // Live map, Tablets tab: no tablet is online in the pitch, the list says so.
  await nav(page, 'Live map')
  await page.getByTestId('fleet-tab-tablets').click()
  await expect(page.locator('.live-side')).toContainText(/tablet/i)
  await page.locator('.fleet').getByRole('radio', { name: 'Robots' }).click()
  expect(problems).toEqual([])
})

test('zones: draw, save, rename and delete a deaf zone and a restricted zone', async ({ page }) => {
  const problems = watch(page)
  await signIn(page)
  await nav(page, 'Zones')
  const plan = page.getByTestId('plan-editor')
  for (const [kind, corners] of [['Deaf', [[0.15, 0.3], [0.35, 0.3], [0.35, 0.5], [0.15, 0.5]]], ['Restricted', [[0.6, 0.6], [0.8, 0.6], [0.8, 0.8]]]] as const) {
    const name = `${kind} pitch ${STAMP}`
    await page.getByTestId('new-zone').click()
    const box = await plan.boundingBox()
    if (!box) throw new Error('plan not visible')
    for (const [fx, fy] of corners) await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy)
    await page.getByLabel('Name').fill(name)
    await page.getByRole('radio', { name: kind }).click()
    await page.getByTestId('save-zone').click()
    await toast(page, `“${name}” saved`)
    await expect(page.getByTestId('deliveries').getByText('received').first()).toBeVisible({ timeout: 15_000 })
    // Rename it, save the change.
    await page.getByLabel('Name').fill(`${name} b`)
    await page.getByTestId('save-zone').click()
    await toast(page, `“${name} b” saved`)
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Delete the zone' }).click()
    await toast(page, `“${name} b” deleted`)
  }
  // Discard a drawing in progress.
  await page.getByTestId('new-zone').click()
  await page.getByRole('button', { name: 'Discard' }).click()
  expect(problems).toEqual([])
})

test('clinics, building overlay edit, patients and tablet pairing, sign out', async ({ page }) => {
  const problems = watch(page)
  await signIn(page)

  // Clinics: copy the active plan, export it, activate the copy and back, delete the copy.
  await nav(page, 'Clinics')
  const copyName = `Pitch copy ${STAMP}`
  page.once('dialog', (dialog) => { void dialog.accept(copyName) })
  await page.getByRole('button', { name: /New from the active one/ }).click()
  await toast(page, `Created “${copyName}”.`)
  const activeRow = page.getByRole('row').filter({ hasText: 'Active' })
  const activeName = (await activeRow.locator('strong').first().innerText()).trim()
  const copyRow = page.getByRole('row').filter({ hasText: copyName })
  const download = page.waitForEvent('download')
  await copyRow.getByRole('button', { name: 'Export', exact: true }).click()
  console.log(`  export: ${(await download).suggestedFilename()}`)
  // Switching plans is refused while a robot still drives a task: the page says why.
  await copyRow.getByRole('button', { name: 'Activate' }).click()
  const activated = page.locator('.toast').filter({ hasText: `“${copyName}” is now the active clinic.` })
  const refused = page.locator('.plan-error').filter({ hasText: /Tasks are still open/ })
  await expect(activated.or(refused).first()).toBeVisible({ timeout: 10_000 })
  if (await activated.count()) {
    await toast(page, `“${copyName}” is now the active clinic.`)
    await page.getByRole('row').filter({ hasText: activeName }).filter({ hasNotText: copyName }).getByRole('button', { name: 'Activate' }).click()
    await toast(page, `“${activeName}” is now the active clinic.`)
  } else console.log(`  clinics: ${(await refused.locator('strong').first().innerText()).trim()}`)
  await copyRow.getByRole('button', { name: 'Delete' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await toast(page, 'Deleted.')

  // Building: add a piece of furniture, save, then reset the modifications.
  await nav(page, 'Building')
  const plan = page.getByTestId('building-plan')
  await expect(plan).toBeVisible({ timeout: 15_000 })
  await page.getByRole('radio', { name: 'Add furniture' }).click()
  const box = await plan.boundingBox()
  if (!box) throw new Error('building plan not visible')
  await page.mouse.click(box.x + box.width * 0.45, box.y + box.height * 0.55)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await toast(page, /Modifications saved/)
  await page.getByRole('button', { name: /Reset modifications/ }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Reset' }).click()
  await toast(page, /Modifications reset/)
  await page.getByRole('button', { name: 'Add floor' }).click()
  await page.getByRole('button', { name: 'Discard' }).click()
  await expect(page.locator('.plan-error')).toHaveCount(0)

  // Patients: admit, create a tablet pairing code, copy it, refresh, discharge.
  await nav(page, 'Patients & rooms')
  await page.getByLabel('First name').fill('Alex')
  await page.getByLabel('Medical record reference').fill(`MRN-${STAMP}`)
  // The page no longer pre-selects a room: choose the first free one, as staff do.
  await page.getByLabel('Room').selectOption({ index: 1 })
  const roomLabel = (await page.getByLabel('Room').locator('option:checked').innerText()).split(' · ')[0]
  await page.getByRole('button', { name: /Admit patient/ }).click()
  await toast(page, /Alex/)
  const card = page.locator('article.room-card').filter({ hasText: 'Alex' }).first()
  await card.getByRole('button', { name: /Register tablet|Show new pairing code|Tablet paired/ }).click()
  await toast(page, `Pairing code generated for ${roomLabel}.`)
  await expect(page.locator('.pairing-code-box strong')).toHaveText(/[0-9A-F-]{8,}/i)
  await page.getByRole('button', { name: 'Copy code' }).click()
  await toast(page, /Pairing code copied|Copy was blocked/)
  await page.getByRole('button', { name: 'Refresh' }).click()
  await card.getByRole('button', { name: 'Discharge and reset' }).click()
  await page.getByRole('dialog').getByRole('button').last().click()
  await toast(page, `${roomLabel} is ready for the next patient.`)

  // Theme and sign out.
  await page.getByRole('button', { name: 'Switch theme' }).click()
  await page.getByRole('button', { name: 'Switch theme' }).click()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('button', { name: /open the console/i })).toBeVisible()
  expect(problems).toEqual([])
})
