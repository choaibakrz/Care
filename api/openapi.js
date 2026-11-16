const document = require('../openapi.json')

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') {
    res.statusCode = 405
    res.setHeader('Allow', 'GET')
    res.setHeader('Content-Type', 'application/json; charset=utf-8')
    return res.end(JSON.stringify({ error: 'method_not_allowed' }))
  }

  res.statusCode = 200
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300')
  res.setHeader('X-Content-Type-Options', 'nosniff')
  return res.end(JSON.stringify(document))
}

module.exports.document = document
