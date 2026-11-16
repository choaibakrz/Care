/**
 * PBKDF2-HMAC-SHA256 with a 32-byte output, in plain TypeScript.
 *
 * HACKATHON: WebCrypto (`crypto.subtle`) exists only in a secure context (https or localhost).
 * A console opened from a LAN address over plain http (another laptop at the pitch) has no
 * `crypto.subtle`, so `deriveAccountKey` falls back to this. Same result, a few seconds slower.
 */

const K = new Int32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

const IV = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

/** One SHA-256 compression: `w[0..16]` holds the block, `state` is updated in place. */
function compress(state: Int32Array, w: Int32Array): void {
  for (let i = 16; i < 64; i++) {
    const a = w[i - 15] ?? 0
    const b = w[i - 2] ?? 0
    const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3)
    const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10)
    w[i] = ((w[i - 16] ?? 0) + s0 + (w[i - 7] ?? 0) + s1) | 0
  }
  let a = state[0] ?? 0
  let b = state[1] ?? 0
  let c = state[2] ?? 0
  let d = state[3] ?? 0
  let e = state[4] ?? 0
  let f = state[5] ?? 0
  let g = state[6] ?? 0
  let h = state[7] ?? 0
  for (let i = 0; i < 64; i++) {
    const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7))
    const ch = (e & f) ^ (~e & g)
    const t1 = (h + S1 + ch + (K[i] ?? 0) + (w[i] ?? 0)) | 0
    const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10))
    const maj = (a & b) ^ (a & c) ^ (b & c)
    const t2 = (S0 + maj) | 0
    h = g
    g = f
    f = e
    e = (d + t1) | 0
    d = c
    c = b
    b = a
    a = (t1 + t2) | 0
  }
  state[0] = ((state[0] ?? 0) + a) | 0
  state[1] = ((state[1] ?? 0) + b) | 0
  state[2] = ((state[2] ?? 0) + c) | 0
  state[3] = ((state[3] ?? 0) + d) | 0
  state[4] = ((state[4] ?? 0) + e) | 0
  state[5] = ((state[5] ?? 0) + f) | 0
  state[6] = ((state[6] ?? 0) + g) | 0
  state[7] = ((state[7] ?? 0) + h) | 0
}

/** SHA-256 of `msg`, continuing from `start` after `prefix` bytes already hashed (a multiple of 64). */
function digestFrom(start: Int32Array, msg: Uint8Array, prefix: number): Int32Array {
  const state = Int32Array.from(start)
  const total = msg.length + 9
  const padded = new Uint8Array(Math.ceil(total / 64) * 64)
  padded.set(msg)
  padded[msg.length] = 0x80
  const bits = (prefix + msg.length) * 8
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length - 8, Math.floor(bits / 0x100000000))
  view.setUint32(padded.length - 4, bits >>> 0)
  const w = new Int32Array(64)
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getInt32(off + i * 4)
    compress(state, w)
  }
  return state
}

function wordsToBytes(words: Int32Array): Uint8Array {
  const out = new Uint8Array(words.length * 4)
  const view = new DataView(out.buffer)
  words.forEach((word, i) => view.setInt32(i * 4, word))
  return out
}

/** PBKDF2-HMAC-SHA256(password, salt, iterations), first 32 bytes. */
export function pbkdf2Sha256(password: Uint8Array, salt: Uint8Array, iterations: number): Uint8Array {
  const key = new Uint8Array(64)
  key.set(password.length > 64 ? wordsToBytes(digestFrom(Int32Array.from(IV), password, 0)) : password)
  const w = new Int32Array(64)
  const keyView = new DataView(key.buffer)
  const inner = Int32Array.from(IV)
  const outer = Int32Array.from(IV)
  for (let i = 0; i < 16; i++) w[i] = keyView.getInt32(i * 4) ^ 0x36363636
  compress(inner, w)
  for (let i = 0; i < 16; i++) w[i] = keyView.getInt32(i * 4) ^ 0x5c5c5c5c
  compress(outer, w)

  const first = new Uint8Array(salt.length + 4)
  first.set(salt)
  first[salt.length + 3] = 1
  let u = digestFrom(outer, wordsToBytes(digestFrom(inner, first, 64)), 64)
  const t = Int32Array.from(u)
  // Every later round hashes one 32-byte value: a single fixed-shape block per HMAC half.
  const state = new Int32Array(8)
  for (let round = 1; round < iterations; round++) {
    for (let half = 0; half < 2; half++) {
      w.set(u)
      w[8] = 0x80000000 | 0
      w.fill(0, 9, 15)
      w[15] = (64 + 32) * 8
      state.set(half === 0 ? inner : outer)
      compress(state, w)
      u = Int32Array.from(state)
    }
    for (let i = 0; i < 8; i++) t[i] = (t[i] ?? 0) ^ (u[i] ?? 0)
  }
  return wordsToBytes(t)
}
