const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const { URL } = require('node:url')
const { isAllowedOrigin } = require('./api/_supabase')

const PORT = Number(process.env.PORT) || 8080
const HOST = process.env.HOST || '0.0.0.0'
const PATIENT_ROOT = path.resolve(__dirname, 'implementation/patient-web')
const MAX_BODY_BYTES = 1_000_000

const MIME_TYPES = {
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp'
}

const API_HANDLERS = new Map([
  ['/api/auth/login', './api/auth/login.js'],
  ['/api/auth/logout', './api/auth/logout.js'],
  ['/api/auth/profile', './api/auth/profile.js'],
  ['/api/auth/request-otp', './api/auth/request-otp.js'],
  ['/api/auth/session', './api/auth/session.js'],
  ['/api/auth/signup', './api/auth/signup.js'],
  ['/api/auth/verify-otp', './api/auth/verify-otp.js'],
  ['/api/admin/login', './api/admin/login.js'],
  ['/api/admin/rooms', './api/admin/rooms.js'],
  ['/api/admin/devices', './api/admin/devices.js'],
  ['/api/admin/discharge', './api/admin/discharge.js'],
  ['/api/room/pair', './api/room/pair.js'],
  ['/api/room/session', './api/room/session.js'],
  ['/api/room/unpair', './api/room/unpair.js'],
  ['/api/patient/mood', './api/patient/mood.js'],
  ['/api/patient/program', './api/patient/program.js'],
  ['/api/patient/questions', './api/patient/questions.js'],
  ['/api/patient/requests', './api/patient/requests.js'],
  ['/api/openapi', './api/openapi.js'],
  ['/api/openapi.json', './api/openapi.js']
])

function setSecurityHeaders(res) {
  res.setHeader('X-Content-Type-Options', 'nosniff')
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin')
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
}

function sendJson(res, status, body) {
  setSecurityHeaders(res)
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify(body))
}

function setCorsHeaders(req, res) {
  const origin = String(req.headers.origin || '').replace(/\/$/, '')
  if (!origin || !isAllowedOrigin(req)) return
  res.setHeader('Access-Control-Allow-Origin', origin)
  res.setHeader('Access-Control-Allow-Credentials', 'true')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS')
  res.setHeader('Vary', 'Origin')
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks = []
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > MAX_BODY_BYTES) {
        reject(Object.assign(new Error('Request body is too large.'), { statusCode: 413 }))
        req.destroy()
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

async function parseJsonBody(req) {
  if (!['POST', 'PUT', 'PATCH'].includes(req.method)) return {}
  const raw = await readBody(req)
  if (!raw.length) return {}
  try {
    return JSON.parse(raw.toString('utf8'))
  } catch {
    throw Object.assign(new Error('Request body must be valid JSON.'), { statusCode: 400 })
  }
}

function resolveHandler(pathname) {
  const direct = API_HANDLERS.get(pathname)
  if (direct) return direct
  if (/^\/api\/patient\/questions\/[^/]+$/.test(pathname)) return './api/patient/questions/[id].js'
  return null
}

async function handleApi(req, res, pathname) {
  const handlerPath = resolveHandler(pathname)
  if (!handlerPath) return false

  try {
    const questionMatch = pathname.match(/^\/api\/patient\/questions\/([^/]+)$/)
    if (questionMatch) req.query = { id: decodeURIComponent(questionMatch[1]) }
    req.body = await parseJsonBody(req)
    const handler = require(path.resolve(__dirname, handlerPath))
    res.status = (status) => { res.statusCode = status; return res }
    await handler(req, res)
    if (!res.writableEnded) res.end()
  } catch (error) {
    if (res.writableEnded) return true
    const status = Number.isInteger(error.statusCode) ? error.statusCode : 500
    if (status >= 500) console.error(`API error on ${req.method} ${pathname}:`, error)
    sendJson(res, status, { error: status === 500 ? 'internal_error' : 'invalid_request', message: error.message })
  }
  return true
}

function safeStaticPath(pathname) {
  const requested = pathname === '/' ? '/index.html' : pathname
  const cleanPath = requested.endsWith('/') ? `${requested}index.html` : requested
  const candidate = path.resolve(PATIENT_ROOT, `.${cleanPath}`)
  if (candidate !== PATIENT_ROOT && !candidate.startsWith(`${PATIENT_ROOT}${path.sep}`)) return null
  return candidate
}

function findStaticFile(pathname) {
  const candidates = [safeStaticPath(pathname)]
  if (!path.extname(pathname) && pathname !== '/') candidates.push(safeStaticPath(`${pathname}.html`))
  return candidates.find((candidate) => candidate && fs.existsSync(candidate) && fs.statSync(candidate).isFile()) || null
}

function serveStatic(req, res, pathname) {
  const filePath = findStaticFile(pathname)
  if (!filePath) return sendJson(res, 404, { error: 'not_found' })
  setSecurityHeaders(res)
  const extension = path.extname(filePath).toLowerCase()
  res.statusCode = 200
  res.setHeader('Content-Type', MIME_TYPES[extension] || 'application/octet-stream')
  res.setHeader('Cache-Control', extension === '.html' ? 'no-store' : 'public, max-age=3600')
  if (req.method === 'HEAD') return res.end()
  fs.createReadStream(filePath).on('error', () => {
    if (!res.headersSent) sendJson(res, 500, { error: 'file_read_failed' })
    else res.destroy()
  }).pipe(res)
}

function createServer() {
  return http.createServer(async (req, res) => {
    setSecurityHeaders(res)
    setCorsHeaders(req, res)
    const requestUrl = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`)
    const { pathname } = requestUrl

    if (req.method === 'OPTIONS') {
      res.statusCode = 204
      return res.end()
    }
    if (pathname === '/healthz' || pathname === '/healthz/') {
      return sendJson(res, 200, { ok: true, service: 'spectrum-patient-portal' })
    }
    // Cloud Run's front end can reserve the exact /healthz path. Keep an
    // application-owned probe for deployments and smoke tests.
    if (pathname === '/api/healthz') {
      return sendJson(res, 200, { ok: true, service: 'spectrum-patient-portal' })
    }
    if (pathname.startsWith('/api/')) {
      if (await handleApi(req, res, pathname)) return
      return sendJson(res, 404, { error: 'not_found' })
    }
    if (!['GET', 'HEAD'].includes(req.method)) return sendJson(res, 405, { error: 'method_not_allowed' })
    return serveStatic(req, res, pathname)
  })
}

if (require.main === module) {
  createServer().listen(PORT, HOST, () => console.log(`Spectrum patient portal listening on ${HOST}:${PORT}`))
}

module.exports = { createServer, findStaticFile, resolveHandler }
