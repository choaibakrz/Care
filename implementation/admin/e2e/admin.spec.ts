import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function signIn(page: Page): Promise<void> {
  await page.goto('/')
  await page.getByLabel('Username').fill('admin')
  await page.getByLabel('Password').fill('demo')
  await page.getByRole('button', { name: /open the console/i }).click()
  await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible()
  await expect(page.getByTestId('fleet-R1')).toBeVisible()
}

test('login refuses empty credentials and opens the console with any demo pair', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Username').fill('')
  await page.getByRole('button', { name: /open the console/i }).click()
  await expect(page.getByRole('heading', { name: 'Live map' })).toHaveCount(0)
  await signIn(page)
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  expect(page.url()).not.toContain('token')
})

test('emergency stop is on every page and reports each robot as confirmed stopped', async ({ page }) => {
  await signIn(page)
  for (const name of ['Tasks', 'Zones', 'Stock', 'Audit log']) {
    await page.getByRole('link', { name }).click()
    await expect(page.getByTestId('estop-all')).toBeVisible()
  }
  await page.getByTestId('estop-all').click()
  const report = page.getByTestId('estop-panel')
  await expect(report).toBeVisible()
  await expect(report.getByText('Confirmed stopped')).toHaveCount(4, { timeout: 10000 })
  await expect(report.getByText('Robots stopped')).toBeVisible()
})

test('emergency stop says "use the physical button" when the server cannot be reached', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'System' }).click()
  await page.getByTestId('demo-outage').click()
  await expect(page.getByText('No connection to the server.')).toBeVisible()
  await page.getByTestId('estop-all').click()
  const report = page.getByTestId('estop-panel')
  await expect(report.getByText('Use the physical red button on the robot now.')).toBeVisible({ timeout: 10000 })
  await expect(report.getByText('FAILED').first()).toBeVisible()
})

test('the panel recovers by itself when the server comes back', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'System' }).click()
  await page.getByTestId('demo-outage').click()
  await expect(page.getByText('No connection to the server.')).toBeVisible()
  await expect(page.getByText('No connection to the server.')).toHaveCount(0, { timeout: 30000 })
  await expect(page.getByText('Connection restored. Data is up to date again.')).toBeVisible()
})

test('an admin draws a deaf zone, saves it, and every robot receives it', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'Zones' }).click()
  await page.getByTestId('new-zone').click()
  const plan = page.getByTestId('plan-editor')
  const box = await plan.boundingBox()
  if (!box) throw new Error('plan not visible')
  for (const [fx, fy] of [[0.12, 0.45], [0.3, 0.45], [0.3, 0.6], [0.12, 0.6]]) await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy)
  await page.getByLabel('Name').fill('Corridor west · e2e')
  await page.getByTestId('save-zone').click()
  await expect(page.getByText('“Corridor west · e2e” saved.')).toBeVisible()
  await expect(page.getByTestId('deliveries').getByText('received')).toHaveCount(4, { timeout: 10000 })
  await page.getByRole('link', { name: 'Audit log' }).click()
  await expect(page.getByText('Zone created')).toBeVisible()
})

test('a robot that stops talking turns grey after five seconds', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'System' }).click()
  await page.getByTestId('demo-drop').click()
  await page.getByRole('link', { name: 'Live map' }).click()
  await page.getByTestId('fleet-R1').click()
  await expect(page.getByTestId('fleet-R1').getByText('No signal')).toBeVisible({ timeout: 10000 })
  await expect(page.getByTestId('robot-detail').getByText(/last one known, not a live one/)).toBeVisible()
})

test('emergency mode: one click on, banner on every page, changes refused, two clicks off', async ({ page }) => {
  await signIn(page)
  await expect(page.getByTestId('mode-switch')).toBeEnabled()
  await page.getByTestId('mode-switch').click()
  await expect(page.getByTestId('emergency-banner')).toBeVisible()
  await page.getByRole('link', { name: 'Stock' }).click()
  await expect(page.getByTestId('emergency-banner')).toBeVisible()
  await expect(page.getByRole('button', { name: /One more/ }).first()).toBeDisabled()
  await expect(page.getByTestId('estop-all')).toBeVisible()
  await page.getByTestId('mode-switch').click()
  await expect(page.getByTestId('mode-confirm')).toBeVisible()
  await page.getByTestId('mode-exit').click()
  await expect(page.getByTestId('emergency-banner')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /One more/ }).first()).toBeEnabled()
})

test('a staff tablet can be freed and handed to someone else', async ({ page }) => {
  await signIn(page)
  await page.getByTestId('fleet-tab-tablets').click()
  await page.getByTestId('tablet-tab-dr-a').click()
  await page.getByTestId('tablet-free').click()
  await page.getByRole('button', { name: 'Free the tablet' }).click()
  await expect(page.getByTestId('tablet-assign')).toBeVisible()
  await page.getByLabel('Pseudonym').fill('Dr. C')
  await page.getByTestId('tablet-assign').click()
  await expect(page.getByRole('heading', { name: 'Dr. C' })).toBeVisible()
  await expect(page.getByTestId('tablet-free')).toBeVisible()
})

test('an attack is blocked automatically and an address can be blocked by hand', async ({ page }) => {
  await signIn(page)
  await page.getByRole('link', { name: 'Monitor' }).click()
  await page.getByTestId('demo-attack').click()
  await expect(page.getByTestId('clients-table').getByRole('row', { name: /203\.0\.113\.42/ }).getByText('Blocked')).toBeVisible({ timeout: 15000 })
  await page.getByTestId('block-target').fill('10.0.3.12')
  await page.getByLabel('Reason (kept in the audit log)').fill('Test')
  await page.getByTestId('block-add').click()
  await expect(page.getByText(/robots must stay reachable/).first()).toBeVisible()
})

test('a patient alarm shows on every page and on the map, and cannot be acknowledged here', async ({ page }) => {
  await signIn(page)
  await page.locator('.sidebar').getByRole('link', { name: /Incidents/ }).click()
  await page.getByTestId('demo-alarm').click()
  await expect(page.getByTestId('alarm-banner')).toContainText('Urgent patient call')
  await page.getByRole('link', { name: 'Stock' }).click()
  await expect(page.getByTestId('alarm-banner')).toBeVisible()
  await page.getByRole('link', { name: 'Live map' }).click()
  await expect(page.getByTestId('floor-incident-2')).toBeVisible()
  const alarm = page.locator('.incidents-panel .incident', { hasText: 'Urgent patient call' })
  await expect(alarm.getByText('In the emergency service')).toBeVisible()
  await expect(alarm.getByRole('button', { name: /On it|Close/ })).toHaveCount(0)
  await alarm.locator('.incident-main').click()
  await expect(page.locator('.incident-tag', { hasText: 'Urgent patient call' })).toBeVisible()
})

test('typing and Enter on the login screen before the scripts load are kept', async ({ page }) => {
  let release: () => void = () => undefined
  const gate = new Promise<void>((resolve) => { release = resolve })
  await page.route(/\/src\/main\.tsx/, async (route) => { await gate; await route.continue() })
  await page.goto('/', { waitUntil: 'commit' })
  await page.locator('#boot-username').fill('admin')
  await page.locator('#boot-password').fill('demo')
  await page.locator('#boot-password').press('Enter')
  await expect(page.locator('#boot-submit')).toHaveText('Starting the console…')
  release()
  await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible({ timeout: 30000 })
})
