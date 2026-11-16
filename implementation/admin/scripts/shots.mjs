// Captures every screen of the admin panel for visual review.
// Usage: node scripts/shots.mjs <baseUrl> <outDir> [width] [height]
import { chromium } from '@playwright/test'

const [baseUrl = 'http://localhost:5174', outDir = 'shots', width = '1440', height = '900'] = process.argv.slice(2)
const routes = [['overview', '/'], ['tasks', '/tasks'], ['zones', '/zones'], ['stock', '/stock'], ['night', '/night'], ['audit', '/audit'], ['system', '/system']]

const browser = await chromium.launch({ channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: Number(width), height: Number(height) } })
const errors = []
page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`))
page.on('console', (message) => { if (message.type() === 'error') errors.push(`console: ${message.text()}`) })
page.on('requestfailed', (request) => errors.push(`requestfailed: ${request.url()}`))
const external = new Set()
page.on('request', (request) => { const url = new URL(request.url()); if (!['localhost', '127.0.0.1'].includes(url.hostname) && url.protocol.startsWith('http')) external.add(url.origin) })

await page.goto(baseUrl)
await page.screenshot({ path: `${outDir}/login.png` })
await page.locator('form button[type=submit]').click()
await page.waitForTimeout(3500)
for (const [name, route] of routes) {
  await page.evaluate((path) => { window.history.pushState({}, '', path); window.dispatchEvent(new PopStateEvent('popstate')) }, route)
  await page.waitForTimeout(name === 'overview' ? 4000 : 1200)
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: true })
}
await browser.close()
process.stdout.write(`${JSON.stringify({ errors: [...new Set(errors)].slice(0, 20), external: [...external] }, null, 2)}\n`)
