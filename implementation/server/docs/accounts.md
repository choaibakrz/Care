# Pseudonymous accounts (Task A7)

The server never learns who a user is. The user name and the password never leave the
device: the client derives an **account key** from them and sends only that key. The server
keeps only `HMAC-SHA256(pepper, account_key)`, the **account id**. If the database leaks, no
record says whose it is. (Text a user writes that contains names stays readable: this is an
extra layer, not end-to-end encryption.)

## The derivation (every client implements exactly this)

```
account_key = PBKDF2-HMAC-SHA256(
    password   = UTF-8 bytes of NFC(password) (nothing trimmed),
    salt       = UTF-8 bytes of "clinic:" + clinic_id + ":" + lowercase(NFC(username)),
    iterations = 600000,
    length     = 32 bytes)
```

- `NFC` is Unicode normalisation form C (ruling R25), applied first to the user name and
  to the password: a decomposed "é" (`e` + U+0301) typed on one keyboard gives the same key
  as the composed "é" (U+00E9) typed on another. JavaScript `s.normalize("NFC")`, Dart
  `unorm_dart` `nfc(s)`, Rust `unicode-normalization` `s.nfc()`.
- `lowercase` is then the Unicode default lower-case mapping: JavaScript
  `String.prototype.toLowerCase()`, Dart `String.toLowerCase()`, Rust `str::to_lowercase()`.
  Nothing else is done to the user name (clients trim the input field before deriving).
- `clinic_id` is this server's account clinic id (`ACCOUNT_CLINIC_ID`, default
  `demo-clinic`). It is not a plan id and never changes for an installation; changing it
  changes every key, so everyone would have to enrol again.
- The key is sent as **64 lowercase hex characters**.
- `GET /auth/derivation` (public) returns the parameters:
  `{"algorithm":"PBKDF2-HMAC-SHA256","iterations":600000,"key_bytes":32,"clinic_id":"demo-clinic","salt":"clinic:demo-clinic:<lowercase(NFC(username))>","normalization":"NFC"}`.
- Browser: `password.normalize("NFC")`, `username.normalize("NFC").toLowerCase()`, then
  WebCrypto `deriveBits({name: "PBKDF2", hash: "SHA-256", salt, iterations: 600000}, key, 256)`
  (no extra library, works offline). Flutter: the equivalent PBKDF2 of the `cryptography`
  package. It takes about 0.3 to 1 s on a tablet, once per login.

### Test vectors

Computed by `security::derive_account_key` (the Rust reference) and checked against this
file by `tests/accounts.rs::derivation_test_vector_matches_docs`. Every client must give the
same keys. In a `vector` block, `\u{XXXX}` stands for the code point U+XXXX (so a decomposed
accent survives editors that normalise the file).

```vector
username: Nurse.Example
password: correct horse battery staple
clinic_id: demo-clinic
account_key: 944e5f69478ecbcb2ab4b779ae9391ac89f3c4cbebca198d82398805115f993d
```

The second vector checks UTF-8 and the lower-casing of non-ASCII letters (salt
`clinic:demo-clinic:ärztin.zoé`):

```vector
username: Ärztin.Zoé
password: pässwörd-λ
clinic_id: demo-clinic
account_key: 5a0d8b2dd37938677fd7f511396ae928410ea8b0f442e2df54d316601ad3f8fa
```

The third vector is the second one typed with **decomposed** accents (`A` + U+0308,
`e` + U+0301, `a` + U+0308, `o` + U+0308): NFC makes it the same key.

```vector
username: A\u{0308}rztin.Zoe\u{0301}
password: pa\u{0308}sswo\u{0308}rd-λ
clinic_id: demo-clinic
account_key: 5a0d8b2dd37938677fd7f511396ae928410ea8b0f442e2df54d316601ad3f8fa
```

The `--mock` demo accounts are the derivation of `admin`, `nurse`, `doctor`, `therapist`,
`reception` with the password `mock` and clinic id `demo-clinic` (for example `admin` →
`0840a2acb742ff183c54960bd29738c2081adb0ea76d396e6cfbc2c00e0f1736`).

## What the server stores

- `accounts(id, role, display_label, created_at, disabled)`: `id` is
  `HMAC-SHA256(pepper, account_key)` in hex; `display_label` is a **pseudonym** of at most 32
  characters ("Nurse 7"), never a real name; `#` (the tag separator) and control
  characters are refused (422 `invalid_field`). No user name, e-mail, real name, password or
  account key exists anywhere on the server (database, journal, logs).
- `enrolment_codes(id, code_hash, role, suggested_label, created_at, expires_at, used_at)`:
  only the HMAC of a code.
- The **pepper** is a 32-byte key file (`ACCOUNT_PEPPER`, default `keys/account.pepper`),
  outside the database, like the journal key, never logged. Created on first start in live
  mode with `create_new` (`O_CREAT | O_EXCL`: an existing path is never overwritten or
  followed) and Unix mode `0600` **given at creation** (not a `chmod` afterwards); the 64 hex
  digits are written and `fsync`ed before the pepper is used. On load, a symbolic link is
  refused, and so is a file other users can read (Unix mode `& 077`). On Windows the ACL is
  not checked: the server logs a warning at startup saying so; keep the server's directory
  private. **Back it up with the journal key**: without it no account can log in.
- People see an account as `"<pseudonym> #<tag>"`, the tag being the first 6 hex digits of the
  id (`"Nurse 7 #3fa9c1"`): task `requested_by`, tablet owners, audit actors,
  `LoginResponse.operator`. Inside the server an account is a `UserId` made of the 64 hex
  digits of its id.

## Login

`POST /auth/login {"account_key": "<64 hex>", "device_id": "<optional>"}` →
`{token, role, operator, expires_at}`. The server computes the id, compares it in constant
time, refuses a disabled account. A wrong password is just an unknown key: unknown key, wrong
password and disabled account give the same 401 `invalid_credentials`.

A `{username, password}` body is 422 `key_derivation_required` on the live server: the client
must derive the key. **Mock compatibility until frontend task F9:** `clinic-server --mock`
still accepts `{username, password}` (and the aliases `u-admin`, …) and derives the key
itself; it is the only place a server ever derives a key.

## Enrolment (the server never learns a name)

1. An admin creates a one-time code: `POST /admin/enrolment-codes {"role": "nurse", "label":
   "Nurse 7"}` → 201 `{code: "XXXX-XXXX-XXXX", code_id, role, label, expires_at}`. The code is
   shown once; it is valid **24 h**, single use, journaled by `code_id` only.
2. The new user types the code on their own device, chooses a user name and a password there,
   and a pseudonym. The device derives the key and sends `POST /auth/enrol
   {"enrolment_code", "account_key", "display_label"}` → 201 `{account_tag, role, operator}`.
   An unknown, used or expired code is one answer: 403 `enrolment_refused`. Credentials
   that are already an account: 409 `account_exists` (the code stays unused).
3. The user logs in with the same key.

The first admin of a new installation: on first start with no account, the live server issues
a one-time admin enrolment code (24 h) and prints it on stderr only, never through tracing (so
not in the log file, the flight recorder or the journal, which records only its id; step R1,
`RealAuthService::bootstrap_admin_code`). A restart with still no account retires the earlier
code and prints a new one; once an account exists nothing is printed. The pepper file is
created only on a fresh installation; a missing pepper with accounts stored stops the start.

Administration: `GET /admin/accounts` lists pseudonyms and tags (no user name exists to
list); `DELETE /admin/accounts/{account_tag}` disables an account and revokes its tokens (409
`ambiguous_account_tag` if two accounts share a tag, 409 `cannot_disable_self`).

## No recovery

A forgotten password cannot be recovered or reset: the server has nothing to check a person
against. The admin disables the old account and issues a new enrolment code. Data tied to the
old account (tasks it requested, audit rows) stays under the old id and pseudonym.

## Threat model

1. A database leak reveals pseudonyms, roles, enrolment times and what each account id did; it never reveals a user name, password, real name or account key.
2. Without the pepper file the leaked ids cannot be recomputed, so the copy can neither log in nor test password guesses offline.
3. With the pepper too, guessing is still 600 000 PBKDF2 rounds per guess per user name (the salt contains the user name and the clinic id), so weak passwords remain the weak point.
4. A stolen account key is password-equivalent for this server (but not for other sites: the salt binds it to this clinic); it travels only on the clinic network and is never stored.
5. Names a user types into free text (task notes, brain texts) are not protected by this layer.

## Robot commands from non-admins (lead's decision, Task A7)

A nurse may send `pause`, `resume`, `dock` — role permission `robot_control`. `shutdown` is
admin only (permission `robot_shutdown`, ruling R24): anyone else gets 403 `forbidden`.
Every command gets a `command_id` (in `CommandReceipt` and the journal record
`RobotCommandSent`). A command from a non-admin also raises the admin alert
`{type: "alert", level: "warning", kind: "staff_command", message, command: {command_id,
robot_id, command, by, revertible}}`. The admin may revert it:
`POST /robots/{id}/commands/{command_id}/revert` (admin only) → 202
`{reverted_by_command_id}`, which sends the inverse (`pause` → `resume`, `resume` → `pause`,
`dock` → `resume`) and journals `RobotCommandReverted`. An emergency stop (admin only), a
shutdown and an admin's own command are 409 `not_revertible`; a second revert is 409
`already_reverted` — also when two reverts arrive at once: the first reserves the command
under the log's lock before sending, so exactly one inverse goes out (the reservation is
released if the send fails). Only the robot's **latest** command can be reverted: once
another command was sent to that robot, 409 `superseded`. The live server keeps the last
1024 commands in memory for this; `--mock` implements it already.

**An emergency stop is never lifted by others (ruling R24).** While a robot is in
emergency stop, a non-admin `resume` is 409 `estop_latched` ("Only an admin can re-arm a robot
after an emergency stop.") and nothing is sent, and every revert targeting that robot is 409
`estop_latched`. Only an admin's explicit `resume` re-arms it. The robot driver itself
resumes whenever it is told to: the gate is the server's.
