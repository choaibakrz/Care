# Monitoring, attack detection and blocking

Status: **the console is ready, the server has none of it yet.** Each route below that answers 404 shows "The server does not report … yet" on its own panel; the rest of the Monitor page keeps working. Until `GET /stats/service` exists, the service panel computes the same numbers from the tasks the console already has, and says so.

The server is the clinic's main target. The admin must be able to see that it is attacked, see what the server already did about it, and act by hand. The server's existing per-IP rate limiter (`crates/security/src/rate_limit.rs`, `governor`) is the starting point; this file adds what the console needs on top.

All routes are **admin only**, never rate-limited for an authenticated admin, and allowed in emergency mode (an attack can be the cause of the emergency). They hold **no personal data**: addresses, labels of known networks and devices, and counts.

## Detection rules (what the server does on its own)

| Rule | Default | Effect |
| --- | --- | --- |
| Rate limit per client address | 20 requests/s sustained, burst 40 | Excess requests: 429 `rate_limited` (exists). The client shows as `limited`. A `security.alert` `rate_limited` is sent once when it starts. |
| Persistent excess | over the limit 5 s in a row | Automatic block of that address for 10 min, `security.alert` `auto_blocked`. |
| Failed logins | 10 failed `POST /auth/login` from one address within 60 s | Automatic block for 10 min, `security.alert` `login_burst`. |
| A block expires | at `expires_at` | Removed; `security.alert` `unblocked`. |

All numbers are configuration (`.env`), with these defaults. Every automatic block and every manual block or unblock is written to the audit journal (`client_blocked`, `client_unblocked`: target, reason, source, by).

**Never blocked**, by an automatic or a manual rule (the server refuses the rule with 422 `protected_target`):

- the address of the admin making the request (an admin must not lock themselves out);
- loopback (`127.0.0.0/8`, `::1`);
- the address of any connected robot: robots must stay reachable for the emergency stop;
- the emergency service's addresses (`implementation/emergency.md`);
- ranges broader than `/16` (IPv4) or `/48` (IPv6): 422 `range_too_broad`.

A blocked address gets **403 `blocked`** with no other detail, or the connection is closed before TLS for a flood. The WebSocket upgrade is refused the same way.

Where the client address comes from: the peer address, or `X-Forwarded-For` only from the configured known proxies (as `KnownNetworks::resolve` does today).

## Endpoints

### `GET /monitor/summary`

```json
{"started_at": "2026-11-15T06:00:00Z", "uptime_s": 10800, "version": "0.4.0", "robots_connected": 3, "robots_total": 4, "app_clients": 6, "journal_ok": true, "database_ok": true, "requests_per_s": 12.4, "rejected_per_s": 0.3, "p95_ms": 28, "blocked_clients": 1}
```

`requests_per_s`, `rejected_per_s`: over the last 10 s. `p95_ms`: answer time of the last 10 s, `null` if no request. `app_clients`: open `/ws` connections. `journal_ok`/`database_ok`: `null` if not checked (mock mode).

### `GET /monitor/traffic?window_s=300`

One point per second, oldest first, at most 300.

```json
{"step_s": 1, "p95_ms": 31, "points": [{"at": "2026-11-15T09:00:00Z", "accepted": 11, "rejected": 0}, {"at": "2026-11-15T09:00:01Z", "accepted": 12, "rejected": 45}], "rejected_by": {"rate_limited": 45, "unauthorized": 2, "forbidden": 0, "blocked": 0, "emergency_mode": 0, "invalid": 0}}
```

`rejected_by` sums the window. Reasons: `unauthorized` (401), `forbidden` (403 other than a block), `rate_limited` (429), `blocked` (refused by a block rule), `emergency_mode` (503, see `emergency-mode.md`), `invalid` (other 4xx: 400, 404, 413, 422). 5xx are not "refused": they belong in `journal_ok`/logs.

### `GET /monitor/clients?limit=20`

The busiest client addresses of the last 5 minutes, busiest first (`requests_per_s` over the last 10 s, then `rejected`).

```json
[{"ip": "203.0.113.42", "label": null, "requests_per_s": 84.2, "requests": 2410, "rejected": 2300, "login_failures": 0, "status": "blocked", "reason": "Over 20 requests/s for 5 s"},
 {"ip": "10.0.3.12", "label": "Robot R2", "requests_per_s": 1.2, "requests": 360, "rejected": 0, "login_failures": 0, "status": "ok", "reason": null}]
```

`label`: what the server knows the address is, from the known-networks file (`"Ward Wi-Fi"`), a robot session (`"Robot R2"`), or `null` (the console shows "Unknown" in red). **Never a user name**: an address shared by many people must not be tied to one. `status`: `ok`, `limited`, `blocked`. `reason`: why it is limited or blocked.

Memory only: the per-address counters are kept for 5 minutes and never written to disk (they are network data, not activity of a person).

### `GET /security/blocks`

```json
[{"id": "blk-3", "target": "203.0.113.0/24", "reason": "Flooding the login page", "source": "manual", "created_at": "2026-11-15T09:02:00Z", "expires_at": null, "by": "Admin A", "hits": 120}]
```

`source`: `manual` or `auto`. `expires_at`: `null` means until removed. `hits`: requests refused because of this rule.

### `POST /security/blocks`

```json
{"target": "203.0.113.0/24", "reason": "Flooding the login page", "expires_in_s": 3600}
```

`expires_in_s`: `null` for "until removed". Answers 201 with the rule.

| Status | Code | When |
| --- | --- | --- |
| 422 | `invalid_field` | `target` is not an IP or CIDR; `reason` empty or over 200 characters |
| 422 | `protected_target` | it would cover the caller, loopback, a robot or the emergency service (the message says which) |
| 422 | `range_too_broad` | broader than `/16` or `/48` |

Takes effect on the next request, including for open WebSockets of that address (close them).

### `DELETE /security/blocks/{id}`

204. 404 `not_found` if it no longer exists (expired or removed by another admin).

### `GET /stats/service?hours=24`

Counts only, **never a person**: no patient, no staff name, no room-to-person link.

```json
{"hours": 24, "requests": 28, "delivered": 19, "failed": 5, "median_wait_s": 43, "p90_wait_s": 68, "by_item": [{"label": "Water bottle", "count": 4}], "by_place": [{"place": "room-13", "count": 6}], "bedside_online": 3, "bedside_total": 4}
```

Wait = from `requested` to `delivered`. `by_item`, `by_place`: top 6. A place with fewer than 3 requests in the window may be folded into `"other"` if the clinic wants k-anonymity on small wards (the console handles any place id).

### WebSocket `/ws`: `security.alert`

```json
{"type": "security.alert", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T09:01:05Z", "alert": {"at": "2026-11-15T09:01:05Z", "kind": "auto_blocked", "ip": "203.0.113.42", "message": "203.0.113.42 blocked automatically for 10 min: over 20 requests/s for 5 s."}}
```

`kind`: `rate_limited`, `auto_blocked`, `login_burst`, `blocked` (manual), `unblocked`. Sent to **admin** sockets only. `message` is shown as is. At most one `rate_limited` per address per minute, so a flood cannot flood the console too.

## Where the console does this

| What | File |
| --- | --- |
| Page | `src/pages/Monitor.tsx` (polls every 2 s, service every 10 s, only while open) |
| Charts (SVG, validated palette, crosshair, table view) | `src/pages/monitor/charts.tsx`, `src/pages/monitor/monitor.css` |
| Readers | `src/lib/adapt.ts` (`toSummary`, `toTraffic`, `toClient`, `toBlock`, `toServiceStats`, `security.alert`) |
| Client (404 = not on this server) | `src/lib/http.ts` |
| Service numbers from tasks (fallback and demo) | `src/lib/service.ts` |
| Demo traffic, attack and detection (same rules and defaults) | `src/mock/traffic.ts` |
| Tests | `src/mock/traffic.test.ts` |
