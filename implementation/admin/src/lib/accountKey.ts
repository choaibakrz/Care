/**
 * The account key (server `docs/accounts.md`): the user name and the password never leave this
 * computer. The console derives
 *
 *   PBKDF2-HMAC-SHA256(NFC(password), "clinic:" + clinic_id + ":" + lowercase(NFC(username)), 600 000, 32 bytes)
 *
 * with WebCrypto and sends only the 64 lowercase hex digits.
 */

import { pbkdf2Sha256 } from './pbkdf2'

/** What `GET /auth/derivation` tells the clients. */
export interface DerivationParams {
  clinicId: string
  iterations: number
}

/** The defaults of a server with `ACCOUNT_CLINIC_ID` unset (also the `--mock` demo keys). */
export const DEFAULT_DERIVATION: DerivationParams = { clinicId: 'demo-clinic', iterations: 600_000 }

/** Reads the answer of `GET /auth/derivation`; anything unreadable gives the defaults. */
export function toDerivation(value: unknown): DerivationParams {
  const raw = typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
  const clinicId = typeof raw.clinic_id === 'string' && raw.clinic_id ? raw.clinic_id : DEFAULT_DERIVATION.clinicId
  const iterations = typeof raw.iterations === 'number' && raw.iterations > 0 ? raw.iterations : DEFAULT_DERIVATION.iterations
  return { clinicId, iterations }
}

/** The salt text: `clinic:<clinic id>:<lowercase(NFC(username))>`. */
export function derivationSalt(clinicId: string, username: string): string {
  return `clinic:${clinicId}:${username.normalize('NFC').toLowerCase()}`
}

/** The account key as 64 lowercase hex digits. */
export async function deriveAccountKey(username: string, password: string, params: DerivationParams = DEFAULT_DERIVATION): Promise<string> {
  const subtle = globalThis.crypto?.subtle
  const encoder = new TextEncoder()
  if (!subtle) {
    // HACKATHON: plain-http LAN page (no WebCrypto). Same key, computed in TypeScript.
    const salt = encoder.encode(derivationSalt(params.clinicId, username))
    return toHex(pbkdf2Sha256(encoder.encode(password.normalize('NFC')), salt, params.iterations))
  }
  const material = await subtle.importKey('raw', encoder.encode(password.normalize('NFC')), 'PBKDF2', false, ['deriveBits'])
  const bits = await subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt: encoder.encode(derivationSalt(params.clinicId, username)), iterations: params.iterations },
    material,
    256,
  )
  return toHex(new Uint8Array(bits))
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}
