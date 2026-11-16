const { createDevice } = require('./rooms')

module.exports = async function handler(req, res) {
  return createDevice(req, res)
}
