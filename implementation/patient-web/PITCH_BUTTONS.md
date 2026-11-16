# Patient app: pitch button checklist

Checked on the live Rust server (`cargo run`, no `--mock`) at `/patient/`. The browser was Chrome driven by Playwright, at phone size (390x844, touch, iPhone user agent), laptop size (1280x800) and room-tablet size (1024x768, touch).
Script: `implementation/admin/e2e/pitch-patient.mjs`. Last run: 150/150 checks passed. Every control showed a visible result, no console error and no failing request. The only expected answers are the 401s of the session probes.

Re-run (server already started; on first start pass its enrolment code once):

```
cd implementation/admin
PATIENT_BASE=http://localhost:8080 ENROL_CODE=XXXX-XXXX-XXXX SERVER_LOG=<server stderr file> \
LAN_BASE=http://<lan-ip>:8080 node e2e/pitch-patient.mjs
```

"Translate for me" and "Make it simple" (needs clinic-brain with `--features python` and Apertus or
`scripts/fake_apertus.py`, see `PITCH_RUNBOOK.md` 2b; Chrome's fake microphone plays the WAV):

```
cd implementation/admin
PATIENT_BASE=https://<lan-ip>:8443 AUDIO_WAV=<speech .wav> node e2e/pitch-translate.mjs
BRAIN_DOWN=1 PATIENT_BASE=https://<lan-ip>:8443 AUDIO_WAV=<speech .wav> node e2e/pitch-translate.mjs
```

Last run (2026-11-16, fake Apertus, clinic-brain with the zh Piper voice, English SAPI phrase
followed by 6 s of silence, `fr-FR` phone at 390x844): 10/10 and 6/6 (brain stopped) checks passed.
Auto stop after 8.4 s, zh WAV of 134 KB played (currentTime advanced), "Play again" and "Make it
simple" (141 KB WAV) played, French answer had `audio: null` and was read by the browser voice in
`fr`, typed text gave `/speak` 503 `voice_unavailable` then the browser voice, no page error.

## Sign-in page (`login.html`)

| Control | Status |
|---|---|
| "My phone or laptop" / "Room tablet" switch | OK (`#tablet` or `?code=` preselects the tablet) |
| Email / Phone tabs | OK |
| Sign in (email or phone + password) | OK; a wrong password shows "The sign-in details are not valid." |
| "Need an account? Create one" then Create account (email) | OK |
| Create account (phone number) | OK |
| Missing first name / short password / passwords differ | Message shown, nothing sent |
| "Sign in with an SMS code" then Send me a code | OK; dummy SMS: the code is in the server log (`code=123456`) |
| Verify code | OK; a wrong code shows "The code is invalid or has expired." |
| "Use a password instead" | OK |
| Connect tablet (pairing code) | OK; lower case accepted; a wrong code gives a friendly message; a malformed code is caught before sending; the code works once |
| Server unreachable | Every form says "The clinic server cannot be reached…" (code path, not run) |

## App (`index.html`): account (phone/laptop) and room tablet

| Control | Status |
|---|---|
| Header: SOS (hold 5 s) | OK; a short press does nothing. Phones and tablets open the dialler. Laptops only show the alert and the call link, because `tel:` opened a blocking Chrome prompt. |
| SOS: Silence alarm | OK |
| Header: Profile / "Change my name" (account) | OK; the name is saved (`PUT /api/auth/profile`), toast shown, an empty name shows a message, the close button works |
| Header: Profile / "Room details" (tablet) | OK; shows patient, room, tablet |
| Header: Help dialog, "I understand" | OK |
| Language select (6 languages) | OK for fr, ar (right to left), en; de, es, it not clicked |
| Theme select (auto, light, dark) | OK |
| "Ask a nurse to come" | OK, request sent, status card |
| Mood faces 1–5 (2, 3, 5 clicked) | OK (`POST /api/patient/mood` 204); a low mood offers "Yes, let the team know", which sends a care-team request |
| Request cards: water, blanket, wheelchair, interpreter, pain, care-team | OK, each gives a toast and appears in the status card and "My requests" |
| Request status | Advances by itself for the demo: seen after 20 s, on the way after 60 s, done after 3 min (HACKATHON, server side) |
| "How we protect you" | OK (toast) |
| "Next" card | OK, opens My day |
| My day: programme | OK; an account sees the example day ("Example" tag), a tablet sees the room day |
| My day: add / delete question | OK |
| My day: request history row | OK, opens the request on Home |
| Pause: breathing Start/Stop, memory game + New game, sounds rain/waves/hum + Stop | OK |
| Help tab: emergency dialog, interpreter, privacy | OK |
| Sign out (account) | OK, back to sign-in; the app redirects to sign-in afterwards |
| Disconnect this tablet | OK, back to sign-in; the pairing code cannot be reused |
| Tablet in a room with no patient | Requests, mood and questions say "No patient is assigned to this room yet."; the example day is shown; no failing request |
| Session ended elsewhere | The next API call returns to the sign-in page |

## Network

| Check | Status |
|---|---|
| Same server opened through `127.0.0.1` and the Wi-Fi LAN IP | OK; the session cookie belongs to each host (expected) |
| Cross-origin POST with credentials | Accepted (open-network mode is on for the hackathon) |

## Translate for me (Home tile "Translate for me", view `#view-translate`)

Needs the https address on phones (the microphone is only given to secure pages) and the local brain (`clinic-brain`: faster-whisper + Apertus, Piper voices for the spoken answer). Audio goes to the local brain in memory only, never stored, journaled or logged; the spoken answer only lives in the page's memory.

Checked 2026-11-16 in Chrome (Playwright, 390x844 touch, `fr-FR`, fake microphone playing a phrase followed by silence) against a mock of the patient API (`/listen` with and without `audio`, `/speak` 200 and 503, `/simplify`): 16/16 checks passed with a voice and 16/16 without one (browser voice used). Not yet run against the real brain.

| Control | Status |
|---|---|
| Home tiles "Translate for me" (mic) and "Make it simple" (lines icon), last two tiles of the request grid, normal size | Open the same view in Translate or Make-it-simple mode; Home in the bottom bar goes back |
| Toggle "Translate / Make it simple" at the top of the view | Translate: big mic, result card. Make it simple: text box (prefilled with the last translation) and its "Make it simple" button |
| "Into: Français" chip | 17 languages written in their own language, defaults to the device language, remembered on this device |
| Big round button: tap "Talk", tap "Done" | Red with a pulsing ring and a live level bar, "Listening... Tap Done when they finish."; stops by itself after about 2 s of silence (checked: ~7.5 s for a 6.3 s phrase), after 10 s with no voice, and at 30 s |
| Translating | Spinner and "Translating..." |
| Result card | Big text in the patient's language, "Translated automatically - may contain mistakes", the spoken translation plays by itself (audio unlocked during the tap, iOS safe); without a clinic voice the browser voice reads it in that language |
| Play again | Replays the clinic audio; without one, asks `/api/patient/speak`, then falls back to the browser voice |
| "What was said" (folded) | Original text and "They spoke English" in the app language |
| Make it simple | Plain-words card "In simple words", read aloud through `/api/patient/speak` (browser voice if 503) |
| Leaving the view / new recording | Stops the microphone and any playback; a late answer does not play |
| Brain or Apertus down | "Translation isn't available right now. Please ask the care team." |
| Microphone refused / no microphone / http address | One calm sentence and what to do; on http it shows the https address (port 8443) |
| Nothing heard / too long | "I didn't hear anything. Hold the phone closer and try again." / "That was a bit long..." |
| Header SOS at 390 px | Icon-only round button; the label is kept for screen readers (it was cut off as "mair") |

Last run (2026-11-16, real brain + fake Apertus, https): `pitch-translate.mjs` 10/10, brain stopped 6/6, `pitch-patient.mjs` 150/150. Tiles sit right after "Interpreter".
