# Pitch runbook

One server (Rust, `implementation/server`) serves everything: the API, the admin console at
`/admin/`, the patient app at `/patient/` and the live socket at `/ws`. Two simulated robots
("Sunny" and "Pip") drive around the 3D map on their own.

## 1. Build the console (once, after any change in `admin/`)

```sh
cd implementation/admin
npx pnpm install            # first time only
VITE_USE_MOCK=false npx pnpm build     # writes admin/dist, served at /admin/
```

## 2. Start the server

```sh
cd implementation/server
# Pitch seed: only the 2 simulated robots (no offline r1-r4 showing "No signal").
export SEED_DIR=seed-pitch MAP_PATH=seed/clinic_map.json ROLE_CARDS_PATH=seed/role_cards.json
cargo run --release           # live mode: no --mock, no --demo
```

- It listens on `0.0.0.0:8080` (every interface). Allow it through the Windows firewall
  (private network) the first time.
- `SEED_DIR=seed-pitch` only matters for a **fresh** database: robots already in
  `data/clinic.db` stay. For a clean stage, start with an empty data folder (delete or rename
  `data/`, `journal/`, `keys/` in `implementation/server`, or point `DATABASE_URL`,
  `JOURNAL_DIR`, `JOURNAL_KEY`, `ACCOUNT_PEPPER`, `PATIENT_STORE` elsewhere).
- Useful variables: `CLINIC_BIND` (default `0.0.0.0:8080`), `SIM_ROBOTS` (default 2, `0`
  turns the simulation off), `ADMIN_WEB_DIR` (default `../admin/dist`), `PATIENT_WEB_DIR`
  (default `../patient-web`), `HTTPS_PORT` (default 8443, `0` turns https off), `TLS_DIR`
  (default `data/tls`).
- For "Listen & translate" and "Simplify", also set `BRAIN_TOKEN` (24+ characters, the same
  value as the brain below) before `cargo run`. Without the brain the patient app still works
  and shows "Translation is not available right now".

## 2b. Start the brain (listen, translate, simplify)

Three processes on the laptop, all offline: the Apertus model (or the fake), `clinic-brain`
(Python + faster-whisper), and the server above. Details: `server/docs/brain.md`, section
"Run the brain on Windows".

1. **Apertus** on `http://127.0.0.1:8089` (OpenAI-compatible `POST /v1/chat/completions`).
   Without the real model, start the fake (it answers `[French] <text>`, `In simple words: <text>`,
   and a fixed Chinese sentence for Chinese):
   `.venv\Scripts\python.exe implementation\server\scripts\fake_apertus.py 8089`
2. **Whisper model**: faster-whisper `small` must be in the Hugging Face cache
   (`%USERPROFILE%\.cache\huggingface\hub\models--Systran--faster-whisper-small`; present on
   the pitch laptop). On another machine download it once while online:
   `.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"`
3. **One-time DLL copy** (Store Python; PowerShell, repository root): the 4 lines of
   `server/docs/brain.md` that fill `.venv\embed` (already done on the pitch laptop).
4. **Build and start** (PowerShell, `implementation\server`):

```powershell
$repo = (Resolve-Path ..\..).Path
$env:PYO3_PYTHON = "$repo\.venv\Scripts\python.exe"
cargo build --release --bin clinic-brain --features python   # ALWAYS with the feature
$env:PATH       = "$repo\.venv\embed;$env:PATH"
$env:PYTHONHOME = (& "$repo\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)")
$env:PYTHONPATH = "$repo\.venv\embed\DLLs"
$env:BRAIN_TOKEN = "<same 24+ characters as the server>"
$env:APERTUS_URL = "http://127.0.0.1:8089"     # APERTUS_TIMEOUT_S default 15, WHISPER_MODEL default small
.\target\release\clinic-brain.exe
```

- The log must say `clinic-brain engine started status=Up`. `Degraded` names what is missing
  (Apertus not reachable: listening still works, translation does not).
- A `cargo build`/`cargo run` **without** `--features python` overwrites `clinic-brain.exe` with
  the Python-less one (every call "not available"): rebuild with the feature before going on stage.
- Check: `curl -H "Authorization: Bearer <token>" http://127.0.0.1:8091/v1/health` gives
  `{"status":"up","models":["faster-whisper-small","apertus","piper:zh"],...}`.
- Audio goes to the brain in memory only; nothing is stored or logged (HACKATHON marker).

### Voices (the translation read aloud)

- Download once while online (about 1.3 GB, into `models\voices`, git-ignored; `PIPER_VOICES_DIR`
  to put them elsewhere): `.venv\Scripts\python.exe implementation\server\scripts\fetch_voices.py`
  (already done on the pitch laptop; a voice already there is skipped).
- Today only **Chinese (zh)** speaks with the server voice: the other Piper voices need espeak-ng
  (GPL-3.0), turned OFF by the team (`DECISIONS.md`). For every other language the app reads the
  translation with the **browser's voice** (iPhone/Android have fr, de, it, es...; the pitch
  laptop's Chrome has English only). No Croatian voice exists.
- Check: `/v1/health` lists `"piper:zh"` in `models`. Put the Chinese text in a UTF-8 file (an
  inline `-d` with Chinese is mangled by the Windows command line and gives a 0.2 s WAV):
  `{"text":"请吃两片药","lang":"zh"}` in `zh.json`, then `curl -H "Authorization: Bearer <token>"
  -H "Content-Type: application/json" --data-binary @zh.json http://127.0.0.1:8091/v1/speak -o zh.wav`
  gives a WAV of about 1.4 s (63 KB).
- The fake Apertus answers a fixed Chinese sentence (`我头痛三天了。请给我一点水。`) for any
  translation into Chinese, so the zh voice has real Chinese to read on stage.

### Start order (all on the pitch laptop)

1. Fake or real Apertus on 8089 (step 1 above).
2. `clinic-brain` built with `--features python` (step 4), voices in `modelsoices`. Wait for
   `/v1/health` = `up` with `piper:zh`.
3. The server (section 2) with the same `BRAIN_TOKEN`: `https://<lan-ip>:8443/patient/`. Its
   `/health` shows `"brain":"up"`.
4. Phone: open the https address, accept the certificate once, sign in, allow the microphone.

### 60-second demo: "Translate for me"

| Time | Do | The room sees and hears |
|---|---|---|
| 0-10 s | Home, scroll to the last request tile **"Traduire pour moi"** (phone in French). | One plain tile with a microphone; nothing else on Home moved. |
| 10-15 s | "Vers :" choose **中文** (the language of the person in front of the patient). | The big orange **Parler** button. |
| 15-30 s | Tap **Parler** once. A colleague says in English: "I have had a headache for three days. Can I have some water, please?" Then stay silent. | The button turns red with a moving ring; it stops **by itself** about 2 s after the speech. |
| 30-40 s | Nothing to tap. | "Translating..." then the Chinese text, **spoken aloud** by the clinic voice. |
| 40-48 s | Tap **Réécouter**, then **Rendre simple**. | The voice again; the simple-words card, also read aloud. |
| 48-60 s | "Vers :" **Français**, tap **Parler**, speak again. | French text, read by the phone's own voice (no server voice for French yet). Say: "Nothing is recorded or kept; it all runs on this laptop." |

If the brain is stopped, the same tap shows a calm "La traduction n'est pas disponible pour le
moment. Demandez à l'équipe soignante." and the rest of the app keeps working.

## 3. First admin (fresh database only)

The terminal prints once: `FIRST START: ... One-time ADMIN enrolment code: XXXX-XXXX-XXXX`
(valid 24 h, single use). Open the console, choose **"I have an enrolment code"**, type the
code, a user name, a password and a pseudonym. Next time sign in with the user name and password.

## 4. URLs

Find the laptop's LAN address with `ipconfig` ("IPv4 Address"), e.g. `192.168.1.20`.
All devices must be on the same Wi-Fi.

| Who | URL |
|---|---|
| Admin console (stage laptop) | `http://localhost:8080/admin/` |
| Admin console (another laptop) | `http://192.168.1.20:8080/admin/` (works over plain http: the key derivation has a TypeScript fallback, sign-in takes a few seconds) |
| Patient on a phone or laptop | `https://192.168.1.20:8443/patient/` → accept the certificate warning once ("Advanced" → "Proceed" / "Show details" → "visit this website") → "My phone or laptop", sign up with email or phone; allow the microphone when "Listen & translate" asks. Plain `http://192.168.1.20:8080/patient/` works too, but phones then refuse the microphone |
| Room tablet | `http://192.168.1.20:8080/patient/login.html?code=<pairing code>` (code from Console → Patients → room → pairing code) |
| Health check | `http://192.168.1.20:8080/health` |
| API docs | `http://localhost:8080/docs` |

SMS sign-in codes are not sent: the server prints them in its log.
The start log prints the exact phone URLs ("Phones: https://<lan-ip>:8443/patient/ - accept the
certificate warning once"). The self-signed certificate is made at first start in `data/tls/` and
reused; delete that folder if the Wi-Fi address changed and a phone still complains. Check from the
laptop: `curl -k https://192.168.1.20:8443/health`.

Phone over HTTPS, step by step (the microphone only works on https):
1. Phone on the same Wi-Fi; open `https://<lan-ip>:8443/patient/` (the URL from the "Phones:" log line).
2. Android Chrome: "Advanced" → "Proceed to <ip> (unsafe)". iPhone Safari: "Show Details" →
   "visit this website" → "Visit Website". Once per phone and certificate.
3. Sign up or sign in, Home → "Listen & translate", tap the big button, allow the microphone.
4. Let the person speak, tap again: "Heard (<language>)" and "In your language" appear.
   The target is the phone's language; change it with the selector.

## 5. Demo moves that are tested

- Live map: the 2 robots wander with mood emojis (😊 happy, 🚚 busy, 🙉 deaf zone, 🔋 charging,
  🏠 going home, 🚨 alarm, 🛑 stopped, 💤 offline). Drag a robot with the mouse to move it (refused
  inside a restricted zone or outside the floor: it glides back with a message).
- Draw a deaf zone in Zones: a robot inside it shows the deaf mood and its microphone closes.
- "Home / charging place" panel under the fleet list: choose the dock. Emergency mode, the
  dock command and a battery under 20 % send the robots there; back to normal, they wander again.
- Emergency stop and re-arm, tasks, stock, patients, tablet pairing: all walked through by the
  scripts below.

## 6. Re-check before going on stage

```sh
cd implementation/admin
BASE_URL=http://<ip>:8080/admin/ API_URL=http://<ip>:8080 PITCH_USER=<user> PITCH_PASS=<pass> \
  npx pnpm exec playwright test e2e/pitch-live.spec.ts            # 7 tests, console
PATIENT_BASE=http://<ip>:8080 LAN_BASE=http://127.0.0.1:8080 SERVER_LOG=<server stderr file: the SMS code is logged there> \
  ADMIN_USER=<user> ADMIN_PASSWORD=<pass> node e2e/pitch-patient.mjs   # 150 checks, patient app
PATIENT_BASE=https://<ip>:8443 AUDIO_WAV=<speech .wav> \
  node e2e/pitch-translate.mjs                                    # 10 checks: auto stop, zh voice played, play again, simple, fr browser voice
BRAIN_DOWN=1 PATIENT_BASE=https://<ip>:8443 AUDIO_WAV=<speech .wav> \
  node e2e/pitch-translate.mjs                                    # 6 checks, clinic-brain stopped: calm message
```

`pitch-translate.mjs` plays `AUDIO_WAV` through Chrome's fake microphone, as a French phone
(`fr-FR`). Make a WAV with Windows SAPI (PowerShell):
`Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SetOutputToWaveFile("$env:TEMP\phrase.wav"); $s.Speak("I have had a headache for three days."); $s.Dispose()`
(the pitch laptop has only English voices; a French or German voice must be installed in
Windows Settings → Time & language → Speech to test another spoken language).
Chrome loops the file: add a few seconds of silence after the phrase so the automatic stop
(2 s of quiet) can happen, e.g. `.venv\Scripts\python.exe -c "import wave,sys; r=wave.open(sys.argv[1]); p=r.getparams(); f=r.readframes(r.getnframes()); w=wave.open(sys.argv[2],'wb'); w.setparams(p); w.writeframes(f+b'\0\0'*p.framerate*6)" phrase.wav phrase-pause.wav`
(SAPI: pass a 16 kHz mono `SpeechAudioFormatInfo` to `SetOutputToWaveFile` so the 2-byte frames hold).
Screenshots of each step: `admin/test-results/translate-*.png`.

On a fresh server add `ENROL_CODE=<code>` to the first command (it enrols the admin). These
scripts create test patients, zones and tasks: run them on a scratch data folder, not the
stage one.

## 7. HACKATHON markers to restore after the pitch

`grep -rn HACKATHON implementation/server/src implementation/server/crates implementation/admin/src`

| Where | Relaxed for the pitch |
|---|---|
| `server/crates/security/src/cors.rs` | CORS origin list commented out; any origin mirrored with credentials (`open_layer`) |
| `server/crates/security/src/stack.rs` `known_network` | unknown-IP 403 commented out; any network served |
| `server/crates/security/src/origin.rs` `HACKATHON_OPEN` | WebSocket Origin check off (set to `false` to restore) |
| `server/src/patient/mod.rs` `check_origin` | same-origin refusal on patient POST/PUT/DELETE commented out |
| `server/src/lib.rs` `patient_routes` | open CORS layer on the patient routes |
| `server/src/config.rs` | bind `0.0.0.0:8080` instead of `127.0.0.1`; rate 100/s burst 400 instead of 20/40 |
| `server/src/patient/handlers.rs` `DEMO_STATUS_STEPS` | patient request status advances by age (seen 20 s, on the way 60 s, done 3 min) |
| `server/crates/security/tests/stack.rs`, `origin.rs` tests, `tests/patient_api.rs` | refusal tests `#[ignore]` |
| `admin/src/lib/config.ts` | a console served by the server uses its own origin |
| `admin/src/lib/pbkdf2.ts`, `accountKey.ts` | pure-TypeScript PBKDF2 when WebCrypto is missing (plain-http LAN page) |
| `server/seed-pitch/robots.json` | pitch seed without r1-r4 |
| `server/src/tls.rs`, `server/src/main.rs` `start_https` | HTTPS on 8443 with a self-signed certificate (`HTTPS_PORT=0` turns it off; `TLS_CERT`/`TLS_KEY` for a real one) |
| `server/src/patient/translate.rs`, `server/src/brain_process.rs`, `server/src/services/brain.rs`, `crates/python-bindings` | audio passes through to the local brain for transcription (in memory, never stored or logged), against the "no audio on the server" rule |

## 8. Known limits

- The care team does not see patient requests, questions or moods anywhere in the console;
  request status moves by time only.
- Robots never change floor (no lifts in the simulation); a home on another floor makes them
  stop in place. The console's in-browser mock has no go-home behaviour.
- The live server has no night-round schedule ("No schedule"); "Run now" is demo-only.
- Tasks can be cancelled only before the robot sets off; Clinics → Activate is refused while a
  task is open.
- "Open the jury screen" needs `b13_ecran` running on port 8000.
- Not tried on real phone hardware or iPad Safari (iPad shows the call link without auto-dial).
- Each host name gets its own patient session cookie (`localhost` vs the LAN IP).
