const ACCESS_COOKIE = 'clinic_access_token'
const REFRESH_COOKIE = 'clinic_refresh_token'
const ROOM_DEVICE_COOKIE = 'spectrum_room_device'

function getConfig() {
  const url = process.env.APP_SUPABASE_URL || process.env.SUPABASE_URL
  const anonKey = process.env.APP_SUPABASE_PUBLISHABLE_KEY || process.env.APP_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY
  if (!url || !anonKey) throw new Error('Supabase environment variables are missing.')
  return { url: url.replace(/\/$/, ''), anonKey }
}

function getAdminConfig() {
  const url = process.env.APP_SUPABASE_URL || process.env.SUPABASE_URL
  const serviceKey = process.env.APP_SUPABASE_SECRET_KEY || process.env.APP_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !serviceKey) throw new Error('Supabase server key is missing.')
  return { url: url.replace(/\/$/, ''), serviceKey }
}

function json(res, status, body) {
  res.status(status).setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('X-Content-Type-Options', 'nosniff')
  res.end(JSON.stringify(body))
}

function parseCookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').flatMap((part) => {
    const separator = part.indexOf('=')
    if (separator < 0) return []
    return [[part.slice(0, separator).trim(), decodeURIComponent(part.slice(separator + 1).trim())]]
  }))
}

function isSecureRequest(req) {
  const forwardedProtocol = String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim()
  return forwardedProtocol === 'https' || process.env.NODE_ENV === 'production'
}

function cookie(name, value, maxAge, secure) {
  return `${name}=${encodeURIComponent(value)}; Max-Age=${maxAge}; Path=/; HttpOnly; SameSite=Lax${secure ? '; Secure' : ''}`
}

function strictCookie(name, value, maxAge, secure) {
  return `${name}=${encodeURIComponent(value)}; Max-Age=${maxAge}; Path=/; HttpOnly; SameSite=Strict${secure ? '; Secure' : ''}`
}

function setSessionCookies(req, res, session) {
  const secure = isSecureRequest(req)
  const accessMaxAge = Math.max(60, Number(session.expires_in || 3600))
  res.setHeader('Set-Cookie', [
    cookie(ACCESS_COOKIE, session.access_token, accessMaxAge, secure),
    cookie(REFRESH_COOKIE, session.refresh_token, 60 * 60 * 24 * 30, secure)
  ])
}

function clearSessionCookies(req, res) {
  const secure = isSecureRequest(req)
  res.setHeader('Set-Cookie', [
    cookie(ACCESS_COOKIE, '', 0, secure),
    cookie(REFRESH_COOKIE, '', 0, secure)
  ])
}

function setRoomDeviceCookie(req, res, value, maxAge = 60 * 60 * 24 * 30) {
  res.setHeader('Set-Cookie', strictCookie(ROOM_DEVICE_COOKIE, value, maxAge, isSecureRequest(req)))
}

function clearRoomDeviceCookie(req, res) {
  setRoomDeviceCookie(req, res, '', 0)
}

function configuredOrigins() {
  return String(process.env.SPECTRUM_ADMIN_ORIGINS || '')
    .split(',')
    .map((value) => value.trim().replace(/\/$/, ''))
    .filter(Boolean)
}

function isAllowedOrigin(req) {
  const origin = String(req.headers.origin || '').replace(/\/$/, '')
  if (!origin) return true
  const protocol = String(req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim()
  if (origin === protocol + '://' + req.headers.host) return true
  if (configuredOrigins().includes(origin)) return true
  try {
    const parsed = new URL(origin)
    return parsed.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname)
  } catch {
    return false
  }
}

function sameOrigin(req) {
  const origin = req.headers.origin
  if (!origin) return true
  const protocol = String(req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim()
  return isAllowedOrigin(req)
}

async function supabaseFetch(path, init = {}) {
  const { url, anonKey } = getConfig()
  const headers = {
    apikey: anonKey,
    'Content-Type': 'application/json',
    ...(init.headers || {})
  }
  return fetch(`${url}${path}`, { ...init, headers })
}

async function supabaseAdminFetch(path, init = {}) {
  const { url, serviceKey } = getAdminConfig()
  const headers = {
    apikey: serviceKey,
    Authorization: `Bearer ${serviceKey}`,
    'Content-Type': 'application/json',
    ...(init.headers || {})
  }
  return fetch(`${url}${path}`, { ...init, headers })
}

async function responseJson(response) {
  try { return await response.json() } catch { return null }
}

function publicUser(user) {
  if (!user) return null
  return {
    id: user.id,
    email: user.email || null,
    phone: user.phone || null,
    firstName: user.user_metadata?.first_name || null
  }
}

function normalizeFirstName(value) {
  const firstName = String(value || '').trim().replace(/\s+/g, ' ')
  if (!/^[\p{L}\p{M}][\p{L}\p{M}'’ -]{0,39}$/u.test(firstName)) return null
  return firstName
}

async function updateFirstName(accessToken, firstName) {
  return supabaseFetch('/auth/v1/user', {
    method: 'PUT',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ data: { first_name: firstName } })
  })
}

module.exports = {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  ROOM_DEVICE_COOKIE,
  clearSessionCookies,
  clearRoomDeviceCookie,
  getConfig,
  getAdminConfig,
  json,
  parseCookies,
  publicUser,
  normalizeFirstName,
  responseJson,
  sameOrigin,
  isAllowedOrigin,
  setSessionCookies,
  setRoomDeviceCookie,
  strictCookie,
  supabaseAdminFetch,
  supabaseFetch,
  updateFirstName
}
