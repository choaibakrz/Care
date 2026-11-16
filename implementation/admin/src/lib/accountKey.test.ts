import { describe, expect, it } from 'vitest'
import { DEFAULT_DERIVATION, deriveAccountKey, derivationSalt, toDerivation } from './accountKey'
import { pbkdf2Sha256 } from './pbkdf2'

// The published test vectors of implementation/server/docs/accounts.md.
describe('account key derivation', () => {
  it('matches the first vector', async () => {
    expect(await deriveAccountKey('Nurse.Example', 'correct horse battery staple')).toBe('944e5f69478ecbcb2ab4b779ae9391ac89f3c4cbebca198d82398805115f993d')
  })

  it('matches the second vector (UTF-8, non-ASCII lower-casing)', async () => {
    expect(derivationSalt('demo-clinic', 'Ärztin.Zoé')).toBe('clinic:demo-clinic:ärztin.zoé')
    expect(await deriveAccountKey('Ärztin.Zoé', 'pässwörd-λ')).toBe('5a0d8b2dd37938677fd7f511396ae928410ea8b0f442e2df54d316601ad3f8fa')
  })

  it('gives the same key for decomposed accents (third vector)', async () => {
    expect(await deriveAccountKey('Ärztin.Zoé', 'pässwörd-λ')).toBe('5a0d8b2dd37938677fd7f511396ae928410ea8b0f442e2df54d316601ad3f8fa')
  })

  it('gives the mock demo key of admin / mock', async () => {
    expect(await deriveAccountKey('admin', 'mock')).toBe('0840a2acb742ff183c54960bd29738c2081adb0ea76d396e6cfbc2c00e0f1736')
  })

  it('gives the same key without WebCrypto (plain-http LAN page)', () => {
    const enc = new TextEncoder()
    const hex = (b: Uint8Array) => Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
    expect(hex(pbkdf2Sha256(enc.encode('mock'), enc.encode(derivationSalt('demo-clinic', 'admin')), 600_000))).toBe('0840a2acb742ff183c54960bd29738c2081adb0ea76d396e6cfbc2c00e0f1736')
  })

  it('reads GET /auth/derivation, falling back to the defaults', () => {
    expect(toDerivation({ algorithm: 'PBKDF2-HMAC-SHA256', iterations: 600000, key_bytes: 32, clinic_id: 'north-wing' })).toEqual({ clinicId: 'north-wing', iterations: 600000 })
    expect(toDerivation(null)).toEqual(DEFAULT_DERIVATION)
  })
})
