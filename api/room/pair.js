const { pairRoomDevice } = require('../_room')

module.exports = async function handler(req, res) {
  return pairRoomDevice(req, res)
}
