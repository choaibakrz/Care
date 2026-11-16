# Deploy Spectrum on Cloud Run

The repository now includes a small Node HTTP server and a `Dockerfile`. Cloud Run should build the Docker image and run the container on port `8080`.

## Cloud Run form

Use these values in **Create service → Continuously deploy from a repository**:

- Repository: `choaibakrz/LeukerBadHack`
- Branch: `^main$`
- Build type: **Dockerfile**
- Build context directory: `/`
- Dockerfile: `Dockerfile`
- Service name: `spectrum`
- Region: `europe-west1` or the region closest to the clinic
- Container port: `8080`
- Authentication: allow unauthenticated invocations so patients can open the login page; Supabase authentication still protects account and patient API data

Leave **Entrypoint** and **Function target** empty. This image starts with `node server.js`.

## Environment variables

Add these as Cloud Run runtime variables. The first two are used by the patient
portal; the last two are required by the admin room-assignment API:

```text
APP_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
APP_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
APP_SUPABASE_SECRET_KEY=YOUR_SERVER_ONLY_SECRET_KEY
SPECTRUM_ADMIN_EMAILS=admin@example.com
SPECTRUM_ADMIN_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

APP_SUPABASE_SECRET_KEY is server-only. Never put it in VITE_* variables,
the browser bundle, or the admin .env.local file. Do not add the JWT secret
or database password to this service.
SPECTRUM_ADMIN_ORIGINS controls which admin browser origins may call the
administrator API. Add the real admin URL if the admin panel is deployed.

## Health check

Cloud Run can use:

```text
GET /api/healthz
```

It returns HTTP 200 when the container is running. /healthz is also exposed
by the Node server, but /api/healthz is the reliable smoke-test path when a
Google front-end reserves the exact /healthz path.
