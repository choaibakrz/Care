// Usage: node scripts/crop.mjs <baseUrl> <out.png> <route> [clicks...]  — viewport-only shot after optional clicks (css selectors or text=)
import { chromium } from '@playwright/test'
const [baseUrl, out, routeName = 'home', ...steps] = process.argv.slice(2)
const route = routeName === 'home' ? '/' : `/${routeName}`
const browser = await chromium.launch({ channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
await page.goto(baseUrl)
await page.locator('form button[type=submit]').click()
await page.waitForTimeout(2500)
await page.evaluate((path) => { window.history.pushState({}, '', path); window.dispatchEvent(new PopStateEvent('popstate')) }, route)
await page.waitForTimeout(2500)
for (const step of steps) {
  if (step.startsWith('wait=')) await page.waitForTimeout(Number(step.slice(5)))
  else if (step.startsWith('theme=')) await page.evaluate((theme) => { document.documentElement.dataset.theme = theme }, step.slice(6))
  else await page.locator(step).first().click()
  await page.waitForTimeout(700)
}
await page.waitForTimeout(1500)
await page.screenshot({ path: out })
await browser.close()
if (errors.length) console.log(errors.join('\n'))
