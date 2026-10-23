# GIVVI

Next generation application for secret santa event management.

## Idea

This is a demo app to verify how does the AI models iproved over time.
Application has a standard idea and scenario handling.
Project verifies and indirectale measure how does AI affect software development.

## Development Status

Phases 0-2 are verified. Phase 3 implements revocable event invitations and self-service roster claims and is ready for review. Registration signs users in immediately without sending a verification email; password recovery and email-change confirmation remain supported. Wishlist and drawing features remain later-phase work. Each phase is reviewed by the user before the next begins.

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
.venv/bin/flask --env-file .env.example --app givvi db-upgrade
```

If the host lacks Python's `ensurepip` and already has `uv`, use `uv venv .venv --allow-existing --seed` to create the environment, then install requirements with pip as above. Otherwise install the OS's Python venv support before retrying.

The example environment contains local-only placeholders, including an example outbox encryption key. For personal development configuration, use an ignored `.env` and set matching `POSTGRES_PASSWORD` and `GIVVI_DATABASE_URL` values. Generate a private Fernet key for `GIVVI_OUTBOX_KEY`; do not use example values in deployment or commit secrets. Changing that key while messages are queued makes those payloads unreadable. Change port settings and the database URL together if local ports are occupied. Never point integration tests at a production database.

Start the API, frontend, and email worker in separate terminals:

```bash
.venv/bin/flask --env-file .env.example --app givvi run --host 127.0.0.1 --port 5000 --no-reload
```

```bash
npm --prefix frontend run dev
```

```bash
.venv/bin/flask --env-file .env.example --app givvi mail-worker --watch
```

The worker is required for password-reset and email-change messages, not signup. For a single delivery batch, omit `--watch`.

For a personal `.env`, use that file instead of `.env.example` with Flask and Docker Compose. Environment variables override the example file. Vite proxies `/api` to the backend on port 5000.

- Application: http://127.0.0.1:5173/
- API readiness: http://127.0.0.1:5000/api/health/ready
- Mailpit inbox: http://127.0.0.1:8025/
- PostgreSQL: localhost:5433

## Checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m flake8 givvi tests migrations
.venv/bin/python -m isort --check-only givvi tests migrations
GIVVI_TEST_DATABASE_URL=postgresql+psycopg://givvi:replace-with-local-password@127.0.0.1:5433/givvi .venv/bin/python -m pytest -m integration -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The default pytest run selects unit tests. Integration selection requires a real PostgreSQL URL and fails if configuration is missing. Account migration tests use isolated PostgreSQL schemas and check upgrade/downgrade, schema drift, and concurrent requests.

Install the Chromium runtime once from the frontend directory and run browser checks:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

Playwright starts development servers automatically if they are not running. Start the email worker first for account journeys. It uses the example database configuration unless `GIVVI_DATABASE_URL` is supplied. CI installs OS browser dependencies automatically. If your Linux host lacks those libraries, start the API/frontend/worker yourself and use this root-directory command instead:

```bash
docker run --rm --network host --ipc host \
	--user "$(id -u):$(id -g)" -e HOME=/tmp \
	-v "$PWD:/workspace" -w /workspace/frontend \
	mcr.microsoft.com/playwright:v1.63.0-noble npm run test:e2e
```

Screenshots and failure traces are written under the ignored frontend test-results directory. The Docker fallback uses Linux host networking; other environments should install their supported browser dependencies.

## Phase 0 Review

1. Open http://127.0.0.1:5173/status and confirm it reports Connected.
2. Select Polish and confirm the heading, status, and retry control are translated.
3. Optionally stop PostgreSQL with `docker compose --env-file .env.example stop postgres`, use the retry control, and confirm Unavailable. Restore it with `docker compose --env-file .env.example up -d --wait postgres` and retry.
4. Check the layout on a narrow mobile viewport and review the approved defaults in spec section 14.
5. Confirm Phase 0 before implementation proceeds to accounts in Phase 1.

## Phase 1 Review

1. Register a new account at http://127.0.0.1:5173/register. You should arrive at Events already signed in, without checking email.
2. Open Profile, edit your name/language, and verify the saved values. Check English and Polish on desktop and a narrow viewport.
3. Log out and sign in with the same credentials. Duplicate signup must not overwrite or sign into an existing account.
4. Exercise password recovery through the Mailpit inbox; the reset link is single-use and invalidates existing sessions.
5. Change your email from Profile using the current password. The old email remains active until the new inbox confirms the change.
6. Review the Phase 1 checkpoint in the delivery plan before continuing to Phase 2.

## Phase 2 Review

1. Register or sign in at http://127.0.0.1:5173/events and create an event with a name, date, and time zone. English defaults to EUR; Polish defaults to PLN.
2. Open the event. Details are read-only until you select Edit event; Save applies changes and Cancel discards them. Confirm the selected currency remains unchanged if you later change your interface language.
3. Add, rename, and remove unclaimed roster entries. The organizer is not automatically enrolled; each added entry remains marked as unclaimed.
4. Sign in with a different account and open the event URL directly. The event must remain inaccessible, and only its admin can edit details or the roster.
5. Review upcoming, ongoing, and past grouping against the event's time zone, then check the layout on desktop and a narrow mobile viewport.
6. Review the Phase 2 checkpoint in the delivery plan before continuing to Phase 3.

## Phase 3 Review

1. As an event admin, prepare several roster entries, create an invitation link, and send an email invitation. Confirm the email uses the recipient's language when known and English otherwise.
2. Open the invite link in a signed-out browser. Before signing in, it should show only roster names and availability; the token should disappear from the address bar and remain usable through registration or login.
3. Claim an available roster name. The browser should open the event only after the claim succeeds; another account cannot claim the same entry, and one account cannot claim a second entry.
4. As an accepted participant, copy the active invitation link. As the admin, regenerate or revoke it and confirm the old link no longer previews or claims.
5. As the admin, release a mistaken claim. Confirm that participant loses event access and can claim a different available roster entry.
6. Run the PostgreSQL integration checks for migrations, competing claims, and claim-versus-roster-removal. Review the Phase 3 checkpoint in the delivery plan before authorizing Phase 4. Claim-versus-draw race coverage is a Phase 5.1b gate when drawing is implemented.

## Phase 4 Review

1. Open Wishlist and add gifts with both unknown and known prices. Edit a gift, move gifts up and down, and delete one. Repeat in English and Polish; an unknown price should be explicit, and a known price must retain its selected EUR or PLN currency.
2. Create an event with a budget and roster entries for at least two accounts. Invite both accounts and have each claim a roster entry; the organizer must claim an entry separately to participate.
3. As a claimed participant, open the event and select another claimed participant's wishlist. Confirm the roster name and event budget are shown, account names/emails are not, and the view has no edit, reorder, delete, reservation, or purchase controls.
4. Check gifts above, equal to, and below the event budget in the matching currency, plus a gift in the other currency and an unknown-price gift. Only a matching-currency price above budget should be highlighted.
5. As the admin, release a claim while drawing is disabled. Confirm the former member can no longer open event-scoped wishlists. Check the owner and participant views on desktop and a narrow mobile viewport in both languages.
6. Run `.venv/bin/pytest -q`, the PostgreSQL integration suite with `GIVVI_TEST_DATABASE_URL` configured, and `npm --prefix frontend test`. Review the Phase 4 checkpoint before authorizing Phase 5.

## Upgrading Existing Development Data

Stop the API and email worker, run `.venv/bin/flask --env-file .env.example --app givvi db-upgrade`, then restart both. The forward migration retains users/passwords, removes registration-verification state, and invalidates old signup tokens. The worker purges obsolete queued account emails instead of sending dead links. Existing accounts can sign in without an onboarding step. Downgrading restores the old schema but cannot restore removed tokens or previous verification timestamps.

Stop development servers with Ctrl+C and stop dependencies with `docker compose --env-file .env.example down`. Database storage is retained; do not remove the volume unless you deliberately want to erase local data.
