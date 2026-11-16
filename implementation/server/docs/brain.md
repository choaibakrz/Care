# The server-side brain (Task A6)

Staff ask the server for **drafts**: a translation, a plain-language rewrite, a summary of notes, a report of a shift. A person reads every draft before anything is sent anywhere. The robot keeps its own brain and its filtering chain (gardien, prise, `b06` rules); the robot speech round trip through the server (C2 `utterance` / `brain.reply`, Task 20c) is **postponed** and has no route, message or type yet.

Status: contract (Task A6). The HTTP shell, the degradation path, the client and the `--mock` drafts run today. **Hackathon:** the Python engine now runs for the patient app's helpers (transcribe with faster-whisper, translate and simplify with Apertus, `briques/clinique/aide_patient.py`), tested on Windows 11 with the repository's `.venv` (see "Run the brain on Windows"); summaries and reports still use the rules-only step.

## Process layout

```
staff app / console ──HTTP──▶ clinic-server (main)    ──HTTP, loopback, BRAIN_TOKEN──▶ clinic-brain
                                 /brain/*                                               /v1/*
                                 journal: BrainCall only                                 python-bindings (pyo3)
                                                                                         └ briques/clinique/interprete.py
                                                                                         └ briques/clinique/resume.py
                                                                                         └ briques/b06_cerveau (cascade)
```

- **Two processes, one workspace.** `clinic-brain` (`src/bin/clinic_brain.rs`, logic in `src/brain_process.rs`) runs Python and the models (Apertus 8B through the `b06` cascade with its rules-only fallback). An out-of-memory or a crash in a model never takes down task dispatch, the alarm mirror or the emergency stop of `clinic-server`.
- **One interpreter thread, bounded queue.** The bridge (`crates/python-bindings`, Task 20) owns the interpreter on one OS thread; calls wait in a queue of `BRAIN_QUEUE` (default 8; more is 503 `brain_busy`) and each has `BRAIN_CALL_TIMEOUT_S` (default 20 s), counted from the moment the call is queued: it covers the wait in the queue plus the execution. The HTTP handlers call the engine from `spawn_blocking`.
- **The cascade cuts Apertus at 15 s** (`python_bindings::brain::APERTUS_CUTOFF`, the delay `interprete.py` gives Apertus) and lets its rules-only step answer; the draft then comes from the fallback and the health says `degraded` (Task 20b).

## Timeouts, nested outer > inner (ruling R22)

| Layer | Variable | Default | Answer when it runs out |
|---|---|---|---|
| `/brain/*` request (security stack) | `BRAIN_ROUTE_TIMEOUT_S` | 30 s | 408 `timeout` (should never happen: the layers inside answer first) |
| main server waits for the brain | `BRAIN_TIMEOUT_S` | 25 s | 504 `brain_timeout` |
| one brain call, queue wait + execution, plus the brain's HTTP margin (2 s) | `BRAIN_CALL_TIMEOUT_S` | 20 s | 504 `brain_timeout` (from the brain) |
| Apertus inside the cascade | `APERTUS_CUTOFF` (constant) | 15 s | none: the rules step answers, `degraded` |

Every other route keeps `REQUEST_TIMEOUT_S` (10 s). Both programs refuse to start (naming the variable) when a timeout is 0, when `BRAIN_TIMEOUT_S` is not below `BRAIN_ROUTE_TIMEOUT_S`, when `BRAIN_CALL_TIMEOUT_S` + 2 s is not below `BRAIN_TIMEOUT_S`, or when `BRAIN_CALL_TIMEOUT_S` is not above the 15 s cut-off.

## Sizes (ruling R23)

- `/brain/*` requests: up to **1 MiB** (`config::BRAIN_MAX_BODY_BYTES`); every other route keeps `MAX_BODY_BYTES` (64 KiB). Over it: 413 `body_too_large` with the JSON error body.
- `clinic-brain` requests: up to `MAX_SOURCES × MAX_TEXT_CHARS × 6 + 64 KiB` = 20 × 8 000 × 6 + 65 536 = **1 025 536 bytes** (`brain_process::BRAIN_PROCESS_MAX_BODY_BYTES`). 6 bytes per character because JSON writes a control character as `\u00XX`; a UTF-8 character alone is at most 4. A `/v1/report` has at most 20 facts (the main server caps what it gathers, the brain checks). Over it: 413 `body_too_large` as JSON, which the main server answers as its own 413 `body_too_large` (not 502).
- **Offline.** Local models only, the repository's `.venv` (Python 3.13), the bricks imported unchanged. No cloud API.

## Client API (main server, `docs/openapi.yaml`, tag `brain`)

| Call | Who (permission) | Answer |
|---|---|---|
| `POST /brain/translate {text, from?, to}` | every staff role (`use_brain`) | `{draft: true, text, from, to, checks{fixed_terms_ok, numbers_ok}}` |
| `POST /brain/simplify {text, lang, level: plain\|easy}` | every staff role (`use_brain`) | `{draft: true, text, lang, level, simplified}` |
| `POST /brain/summarise {sources[{id, kind, text}], lang}` | doctor, therapist, nurse (`summarise_sources`) | `{draft: true, lang, lines[{text, source}], dropped}` |
| `POST /brain/report {kind: shift\|incident\|robot_activity, from, to, lang}` | admin, doctor (`draft_report`) | `{draft: true, kind, from, to, lang, lines[{text, source}], dropped}` |
| `GET /brain/health` | every staff role (`use_brain`) | `{status: up\|degraded\|down, models, queue, detail?}` |

Why these roles: translating and simplifying for a patient is part of every job at the clinic; care notes are written and read by doctors, therapists and nurses only (the admin and reception read no clinical text, so the admin does not hold `summarise_sources`); reports are for the admin who runs the fleet and the doctor who signs the shift handover. Robots hold none.

Rules:
- Texts: 1 to 8 000 characters; at most 20 sources with unique ids (`[A-Za-z0-9._:-]`, 96 max); a report period after `from`, at most 7 days. Errors are 422 `invalid_field` and never repeat the text.
- `translate` (hackathon) goes through `aide_patient.traduire` (Apertus): any pair among `en fr de it es pt nl ar tr zh ru uk pl sq sr hr ro` (by primary tag: `pt-br` is `pt`); another language is 422 `unsupported_language` ("ask a human interpreter"). `from` is optional: without it Apertus names the source language (`und` when it cannot). Same language as the target: the text comes back unchanged. `checks.numbers_ok` says whether every digit run of the source is in the translation; `checks.fixed_terms_ok` is always `true` (no fixed-terms list for these pairs). The text is not altered.
- `simplify` never adds medical advice; the rewrite is checked against its source (same numbers, nothing added). A failed check returns the original with `simplified: false`: the UI says "could not simplify safely".
- `summarise` and `report` apply `resume.py`'s rule (`garder_les_phrases_sures`): every line names its `source`, and every number of a line is in that source; other lines are dropped and counted in `dropped`. Report sources are server records (`task:<id>`, `incident:<id>`, `robot:<id>`) built from what the caller may see; no audio and no free text from patients go in.
- Errors: brain down 503 `brain_unavailable` (with a short fixed reason), queue full 503 `brain_busy`, too slow 504 `brain_timeout`, a model error 502 `brain_failed`, a body over 1 MiB 413 `body_too_large`. The main server keeps the brain's error **code** but always answers with its own fixed message: the brain's message may repeat a request text (a 422 quoting its input), so it is never forwarded or logged (`BrainClientError::Refused` keeps it in a `BrainMessage` whose `Debug` prints only its length and whose `Display` names status and code only).
- `POST /brain/*` are refused with 503 `journal_unavailable` while the journal cannot write (each call is journaled).
- `--mock` answers with clearly labelled canned drafts ("MOCK TRANSLATION (fr→en) — …", "MOCK SUMMARY — …", "MOCK REPORT — …"), `brain: up`, model `mock (canned drafts, no model)`, and one audit row per call.

## Brain process API (`clinic-brain`, loopback only)

| Call | Body | Answer |
|---|---|---|
| `POST /v1/translate` | `TranslateRequest` | `TranslateResult` |
| `POST /v1/simplify` | `SimplifyRequest` | `SimplifyResult` |
| `POST /v1/summarise` | `SummariseRequest` | `SummaryDraft` |
| `POST /v1/report` | `{request: ReportRequest, facts: [{id, kind, text}]}` (the main server gathers the facts) | `ReportDraft` |
| `POST /v1/transcribe` (hackathon) | raw audio, `Content-Type` `audio/webm`, `audio/ogg`, `audio/mp4` or `audio/wav` (parameters such as `;codecs=opus` ignored), at most 4 MiB and 60 s | `{text, lang (ISO 639-1), duration_s}` |
| `POST /v1/speak` (hackathon) | `{text (1..2000 chars), lang}` | `audio/wav` bytes (16-bit PCM mono); 503 `brain_unavailable` "no voice for this language" |
| `GET /v1/health` | — | `BrainHealth` (200 when `up` or `degraded`; each ready voice is `piper:<lang>` in `models`) |

`/v1/transcribe` errors: another media type or an empty body 422 `invalid_field` (`content_type`, `audio`); a recording that cannot be decoded or lasts over 60 s 422 `invalid_field` (`audio`); over 4 MiB 413; no speech model 503 `brain_unavailable`. Main server side: `BrainClient::transcribe(bytes, content_type) -> Transcription {text, lang, duration_s}` (`Debug` prints the length only).

**Voices (`/v1/speak`, hackathon).** `aide_patient.parler(text, lang)`: a Piper VITS voice read by sherpa-onnx on the interpreter thread, loaded on first use and kept in memory, `length_scale` 1.1 (a little slower, clearer), returned as a 16-bit PCM WAV built in memory (never written, never logged). Voices live in `PIPER_VOICES_DIR` (default `<repo>/models/voices`, git-ignored), filled by `scripts/fetch_voices.py` (one medium voice per language: en fr de it es pt nl ar tr zh ru uk pl ro sr sq; **no Croatian voice exists**). **Limit:** sherpa-onnx 2.x no longer phonemizes text (espeak-ng was removed), so only a voice with a lexicon speaks: today **zh only** (chaowen). The other voices need espeak-ng (GPL-3.0), an option the team turned OFF (`DECISIONS.md`, "Voix"); until that is decided they answer 503 and the patient app reads the text with the browser's voice. Main server side: `BrainClient::speak(text, lang) -> Bytes` (answers up to 16 MiB); the patient routes add `audio` (base64 WAV or `null`) and `POST /api/patient/speak`.

HACKATHON: audio passes through to the local brain for transcription, never stored. This bends the rule "no audio on the server": the recording travels phone → main server → `clinic-brain` → faster-whisper in memory only (a Python `bytes` object, decoded with PyAV into an array, dropped after the call); it is never written to disk, journaled or logged.

The types are in `crates/domain/src/brain.rs`, shared by both processes. Every call needs `Authorization: Bearer <BRAIN_TOKEN>` from a loopback peer: another peer is 403 `loopback_only`, a missing or wrong token 401 `brain_token`. `BRAIN_BIND` must be a loopback address (default `127.0.0.1:8091`), and the main server's `BRAIN_URL` must be one too (`http://127.0.0.1:8091`). Request bodies up to 1 025 536 bytes (see Sizes).

Configuration (`.env` or environment, both processes read the same file):

| Variable | Process | Default |
|---|---|---|
| `BRAIN_TOKEN` | both | none: `clinic-brain` refuses to start; the main server reports `down` ("BRAIN_TOKEN is not set"). At least 24 visible ASCII characters; never printed |
| `BRAIN_URL` | server | `http://127.0.0.1:8091` |
| `BRAIN_ROUTE_TIMEOUT_S` | both (checked) | 30 |
| `BRAIN_TIMEOUT_S` | both (used by the server, checked by the brain) | 25 |
| `BRAIN_BIND` | brain | `127.0.0.1:8091` |
| `BRAIN_REPO_ROOT` | brain | `../..` (the repository root seen from `implementation/server`) |
| `BRAIN_VENV` | brain | `<BRAIN_REPO_ROOT>/.venv` |
| `BRAIN_CALL_TIMEOUT_S` | both (used by the brain, checked by the server) | 20 |
| `BRAIN_QUEUE` | brain | 8 |
| `APERTUS_URL` | brain | `http://127.0.0.1:8089` (OpenAI-compatible: `POST {url}/v1/chat/completions`; health asks `GET {url}/v1/models`) |
| `APERTUS_TIMEOUT_S` | brain | 15 (one Apertus answer; must be below `BRAIN_CALL_TIMEOUT_S`) |
| `WHISPER_MODEL` | brain | `small` (faster-whisper size or a model folder; cpu, int8, VAD filter, language detected) |

```
BRAIN_TOKEN=<24+ characters> cargo run --bin clinic-brain                    # no Python: every call 503
BRAIN_TOKEN=<24+ characters> cargo run --bin clinic-brain --features python  # real models (Task 20b)
```

## Degradation

- **Built without Python** (the default; `pyo3` sits behind the `python` feature, ruling R7 gives `python-bindings` its unsafe-lint exception in Task 20): `clinic-brain` starts with `UnavailableEngine` and answers every `/v1/*` call, health included, with 503 `brain_unavailable`: "…this clinic-brain was built without Python; rebuild it with --features python…". The workspace and every test build and pass on a machine with no Python.
- **Python cannot start** (no venv, an import fails): the same `UnavailableEngine`, with the fixed reason "Python or a brick could not be loaded; see the clinic-brain log" (the error itself goes to the brain's log, never to a client).
- **The main server** probes `GET /v1/health` every 5 s and on `GET /brain/health`. `GET /health` reports `brain: up | degraded | down` (`down` until the first probe, and whenever the brain is not running, not reachable within 500 ms, refuses the token, or runs without Python). `down` never makes the server's own `status` `degraded`: tasks, robots, the map and the emergency stop keep working; brain calls answer 503 `brain_unavailable` with a short fixed reason (`GET /brain/health` `detail`: "BRAIN_TOKEN is not set", "clinic-brain is not running", "clinic-brain refused the server's token", "clinic-brain cannot run its models (see its log)", …); the brain's own longer message stays in the brain's answer to the server and its log.
- **Health of the patient helpers** (hackathon), measured by `aide_patient.etat()` at most every 30 s (cached while calls wait): `up` when the whisper model is loaded or in the local cache **and** Apertus answers `GET /v1/models` within 2 s; `degraded` when only one of them works (`detail` "listening works; translation is not available (Apertus is not reachable)" or "translation works; listening is not available (no speech model)"); `down` when neither. Nothing is downloaded by the health check.
- **Apertus down**: translate and simplify answer 503 `brain_unavailable` ("the translation model (Apertus) is not reachable") within `APERTUS_TIMEOUT_S` (about 2 s when nothing listens); transcription keeps working. No speech model: transcribe is 503, translate and simplify keep working.

## Privacy

Texts sent to the brain pass through both processes **in memory only**:
- never written to the database, the journal, a log or a temporary file;
- every text is a `PrivateText`: its `Debug` prints only its length (`PrivateText(42 chars)`), it has no `Display`, so a `tracing` field or an error message cannot carry it by accident; `BrainToken` prints `***`;
- error messages never repeat a text (422 says which field and why), and the main server never forwards a message of the brain;
- the `Authorization` header to the brain is marked sensitive; the `down` reason (`detail`) is a short fixed phrase, never an exception text or a path (`UnavailableEngine` takes `&'static str` reasons only);
- `clinic-brain` has no request trace layer; the main server's trace layer logs method, path and status only;
- the journal records only `RecordBody::BrainCall {kind, latency_ms, ok}` with the caller as actor (audit row `brain_<kind>`, detail "<latency> ms");
- responses are drafts kept by the client only; the server keeps nothing.

Tested today (`tests/brain.rs`): a sentinel text sent through the mock's translate, simplify and summarise is in no captured log line and no audit row; the domain types print no text in `Debug`; a 422 does not echo the text. Ignored until Task 20d: the same sentinel through the live server and a fake `clinic-brain`, checked against the journal files, the logs and the audit rows.

## Measured

Nothing yet. Task 20b records the latency and memory of each call on the iMac M4 and the MacBook M2 here.

## Run the brain on Windows

The `.venv` is built on the **Microsoft Store Python 3.13** (`pyvenv.cfg` `home = ...\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0`). A program outside the Store package cannot load DLLs from `C:\Program Files\WindowsApps\...`: started with that folder on `PATH`, `clinic-brain.exe` dies at once with STATUS_DLL_NOT_FOUND (`python313.dll`), and with the DLL copied but not `DLLs\`, the import of `aide_patient` fails (`_socket`, `_ssl`, ... are `.pyd` files of that folder). The fix: copy the DLLs once into `.venv\embed` (git-ignored), keep the standard library where it is (reading files there works).

Once (PowerShell, repository root):

```powershell
$base = & .\.venv\Scripts\python.exe -c "import sys; print(sys.base_prefix)"   # the real Store folder
New-Item -ItemType Directory -Force .venv\embed | Out-Null
Copy-Item "$base\python313.dll","$base\python3.dll","$base\vcruntime140.dll","$base\vcruntime140_1.dll" .venv\embed\
Copy-Item -Recurse -Force "$base\DLLs" .venv\embed\
```

Build and run (PowerShell, `implementation\server`):

```powershell
$repo = (Resolve-Path ..\..).Path
$env:PYO3_PYTHON = "$repo\.venv\Scripts\python.exe"          # build: pyo3 reads the version and lib dir from it
cargo build --bin clinic-brain --features python
$env:PATH       = "$repo\.venv\embed;$env:PATH"                 # python313.dll
$env:PYTHONHOME = (& "$repo\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)")   # stdlib (Lib\)
$env:PYTHONPATH = "$repo\.venv\embed\DLLs"                     # .pyd modules, loaded from the copy
$env:BRAIN_TOKEN = "<24+ characters, same as the server>"
$env:APERTUS_URL = "http://127.0.0.1:8089"                       # or the fake below
.\target\debug\clinic-brain.exe
```

A later `cargo build`/`cargo test` without `--features python` overwrites the same `clinic-brain.exe` with the Python-less one (every call 503 "built without Python"): rebuild with the feature before a demo.

The log says `clinic-brain engine started status=Up` (or `Degraded` with the reason). If Python cannot start, the log names the error type (`the Python engine could not start error=...`) and every call is 503.

Without a real Apertus, start the fake (deterministic answers, loopback, logs nothing): `python scripts\fake_apertus.py 8089`. It answers `[German] <text>` for a translation into German, `In simple words: <text>` for a simplification, and `{"lang": "fr", ...}` when asked to detect the language.

**Whisper model.** faster-whisper `small` (int8, about 470 MB) is already in the Hugging Face cache of this machine: `%USERPROFILE%\.cache\huggingface\hub\models--Systran--faster-whisper-small` (snapshot `536b0662...`). On another machine, download it once while online: `.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"`. The model loads on the first transcription (a few seconds), then stays in memory.

Measured on this laptop (Windows 11, CPU, debug build), 2026-11-16, with the fake Apertus:

| Call | Result |
|---|---|
| `GET /v1/health` | `{"status":"up","models":["faster-whisper-small","apertus"],"queue":0}`; fake stopped: `degraded`, "listening works; translation is not available (Apertus is not reachable)" |
| `POST /v1/transcribe`, 7.6 s WAV from Windows SAPI | 5.0 s including the model load; `{"duration_s":7.59,"lang":"en","text":"Bonjour, J.A.I. Malovantra Depuis 3 Jours ..."}`. The machine has **no French voice** (only David, Zira, Mark, en-US), so SAPI read the French sentence with an English voice and whisper heard English; the digits 3 and 2 were kept. Test with a real French speaker before the pitch. |
| `POST /v1/translate {"text":"Prenez 2 comprimés à 8 h.","to":"de"}` | `{"text":"[German] Prenez 2 comprimés à 8 h.","from":"fr","to":"de","checks":{"numbers_ok":true,...}}` |
| `POST /v1/translate` `from` = `to` = `en` | the text unchanged |
| `POST /v1/translate` to `xx` | 422 `unsupported_language` |
| `POST /v1/simplify {"text":"Hypertension arterielle, 140/90 mmHg.","lang":"en"}` | `"In simple words: ...", "simplified": true` |
| translate, simplify with Apertus stopped | 503 `brain_unavailable` "the translation model (Apertus) is not reachable", in 2.3 s |
| `/v1/transcribe` with `text/plain`, or bytes that are not audio | 422 `invalid_field` (`content_type`; `audio`: "the audio could not be decoded") |

The brain's log held only the two start lines: no text, no transcript.
