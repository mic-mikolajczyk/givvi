# GIVVI

Next generation application for secret santa event management.

## Idea

This is a demo app to verify how does the AI models iproved over time.
Application has a standard idea and scenario handling.
Project verifies and indirectale measure how does AI affect software development.

## Development Status

Phase 0 provides the Flask/Vue foundation and a bilingual service-status screen. Authentication, events, drawing, and wishlists are not implemented yet. Each phase is reviewed by the user before the next begins.

- [Product specification](docs/spec.md)
- [Delivery plan](docs/plan.md)
- [Architecture decisions](docs/adr.md)

## Local Setup

Requirements: Python 3.12, Node.js 24, npm, Docker, and Docker Compose. Commands below run from the repository root unless otherwise stated.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
docker compose --env-file .env.example up -d --wait
```

If the host lacks Python's `ensurepip` and already has `uv`, use `uv venv .venv --allow-existing --seed` to create the environment, then install requirements with pip as above. Otherwise install the OS's Python venv support before retrying.

The example environment contains local-only placeholders. For personal development configuration, use an ignored `.env` and set matching `POSTGRES_PASSWORD` and `GIVVI_DATABASE_URL` values. Do not use example values in deployment or commit secrets. Change port settings and the database URL together if local ports are occupied. Never point integration tests at a production database.

Start the API and frontend in separate terminals:

```bash
.venv/bin/flask --env-file .env.example --app givvi run --host 127.0.0.1 --port 5000 --no-reload
```

```bash
npm --prefix frontend run dev
```

For a personal `.env`, use that file instead of `.env.example` with Flask and Docker Compose. Environment variables override the example file. Vite proxies `/api` to the backend on port 5000.

- Application: http://127.0.0.1:5173/
- API readiness: http://127.0.0.1:5000/api/health/ready
- Mailpit inbox: http://127.0.0.1:8025/ (delivery features start in Phase 1)
- PostgreSQL: localhost:5433

## Checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m flake8 givvi tests
.venv/bin/python -m isort --check-only givvi tests
GIVVI_TEST_DATABASE_URL=postgresql+psycopg://givvi:replace-with-local-password@127.0.0.1:5433/givvi .venv/bin/python -m pytest -m integration -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The default pytest run selects unit tests. Integration selection requires a real PostgreSQL URL and fails if configuration is missing. No application tables or migrations exist in Phase 0.

Install the Chromium runtime once from the frontend directory and run browser checks:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

Playwright starts development servers automatically if they are not running. It uses the example database configuration unless `GIVVI_DATABASE_URL` is supplied. CI installs OS browser dependencies automatically. If your Linux host lacks those libraries, start the API/frontend yourself and use this root-directory command instead:

```bash
docker run --rm --network host --ipc host \
	--user "$(id -u):$(id -g)" -e HOME=/tmp \
	-v "$PWD:/workspace" -w /workspace/frontend \
	mcr.microsoft.com/playwright:v1.63.0-noble npm run test:e2e
```

Screenshots and failure traces are written under the ignored frontend test-results directory. The Docker fallback uses Linux host networking; other environments should install their supported browser dependencies.

## Phase 0 Review

1. Open the application and confirm it reports Connected.
2. Select Polish and confirm the heading, status, and retry control are translated.
3. Optionally stop PostgreSQL with `docker compose --env-file .env.example stop postgres`, use the retry control, and confirm Unavailable. Restore it with `docker compose --env-file .env.example up -d --wait postgres` and retry.
4. Check the layout on a narrow mobile viewport and review the approved defaults in spec section 14.
5. Confirm Phase 0 before implementation proceeds to accounts in Phase 1.

Stop development servers with Ctrl+C and stop dependencies with `docker compose --env-file .env.example down`. Database storage is retained; do not remove the volume unless you deliberately want to erase local data.
