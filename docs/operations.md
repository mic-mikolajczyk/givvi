# Operations and Deployment

This guide describes the production Compose setup and recovery controls. It is not evidence that a provider is configured, a deployment has been tested, or a release is approved. Do not deploy until the open gates in [the delivery plan](plan.md) are closed.

## Prerequisites

- A public DNS name for the application, with ports 80 and 443 reachable by Caddy for certificate issuance and renewal.
- A managed PostgreSQL database with TLS enabled, a CA certificate, and separate runtime and migration credentials. The runtime role should have only the permissions needed by the running application; the migration role needs schema-change permissions.
- An SMTP submission service that supports TLS, credentials, and a verified sender address.
- Encrypted, access-controlled database backups and a separately retained deletion-ledger export. Backups containing deleted profile data must expire within 30 days.
- A deployment host with Docker Engine and the Compose plugin. Preserve Caddy's `/data` and `/config` volumes across container replacement.

The repository does not provision managed PostgreSQL, SMTP, monitoring, external alert delivery, off-site backup retention, or a backup schedule. Configure and test those with the chosen providers before use.

## Configuration and Secrets

Set these non-secret variables in the deployment environment, not in a committed file:

| Variable | Purpose |
| --- | --- |
| `GIVVI_DOMAIN` | Public hostname used by Caddy and the application origin |
| `GIVVI_SMTP_HOST` | TLS-enabled SMTP hostname |
| `GIVVI_SMTP_FROM` | Verified sender address |
| `GIVVI_SECRETS_DIR` | Host directory containing the secret files below |
| `GIVVI_API_IMAGE`, `GIVVI_WEB_IMAGE` | Optional immutable image tags for a release |

Provide these files under `GIVVI_SECRETS_DIR`:

| File | Contents |
| --- | --- |
| `database_url` | Runtime SQLAlchemy PostgreSQL URL with `sslmode=verify-full` and `sslrootcert=/run/secrets/database_ca` |
| `migration_database_url` | Migration-role PostgreSQL URL with the same verified TLS settings |
| `database_ca` | CA certificate used to verify the database server hostname and chain |
| `outbox_key` | Private Fernet key used to encrypt queued email payloads |
| `metrics_token` | Random bearer token of at least 32 characters |
| `smtp_username` | SMTP username |
| `smtp_password` | SMTP password |

Restrict the host directory and files to the deployment operator and Docker runtime. Never commit or print secret values. Generate an outbox key with the project's installed cryptography dependency, for example:

```bash
umask 077
install -d -m 0700 "$GIVVI_SECRETS_DIR"
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > "$GIVVI_SECRETS_DIR/outbox_key"
openssl rand -hex 32 > "$GIVVI_SECRETS_DIR/metrics_token"
```

Do not rotate `outbox_key` while encrypted messages remain queued; changing it makes those payloads unreadable. Keep SMTP TLS enabled and verify database certificates and hostnames, rather than replacing `verify-full` with a weaker mode.

## Release Procedure

Use immutable image tags and record the current API/web tags before release. Confirm provider credentials, DNS, firewall rules, database roles/TLS, SMTP delivery, backup jobs, alert routing, and restore access independently.

From the repository root, configure the variables above and run:

```bash
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml build api web
docker compose --profile tools -f deploy/compose.yaml run --rm migrate
docker compose -f deploy/compose.yaml up -d api web worker
```

The migration command uses the separate `migration_database_url`. Run it before starting the new API and worker. Do not run migrations against a production database until the release and rollback have been reviewed.

Check public readiness and container status after deployment:

```bash
curl --fail --show-error "https://${GIVVI_DOMAIN}/api/health/ready"
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs --since=10m api worker web
```

Readiness should return HTTP 200 with `{"status":"ready"}`. Liveness is available at `/api/health/live`; it does not prove database availability. Caddy proxies the frontend and API on the same HTTPS origin. Confirm certificate issuance, renewal, and the HTTPS API path from outside the deployment host before admitting users.

The worker normally runs continuously and retries transient failures with bounded backoff. After correcting an SMTP or database outage, inspect worker logs and restart it if needed:

```bash
docker compose -f deploy/compose.yaml restart worker
docker compose -f deploy/compose.yaml logs --since=10m worker
```

Failed messages reach a terminal state after the configured attempt limit and are logged without message payloads. The `/api/health/metrics` endpoint exposes aggregate outbox counts only when called with the bearer token; keep the token out of command history and logs, and restrict monitoring access at the network layer as well.

## Backups and Recovery

Schedule encrypted PostgreSQL backups and test restores. Keep restorable backups containing deleted profile data for no longer than 30 days. Export the deletion ledger regularly, encrypt it, restrict access, and retain it separately from database snapshots so a restore can replay deletions made after the snapshot.

To export the ledger from the running API container, use a protected destination and avoid shell tracing:

```bash
umask 077
docker compose -f deploy/compose.yaml exec -T api flask --app givvi export-deletion-ledger > "$GIVVI_LEDGER_FILE"
```

For recovery, first restore the database snapshot to an isolated database that is not reachable by users or production services. Configure a separate restore-time secret directory so the command targets only that isolated database. Upgrade its schema as required by the recovery procedure, then import the newest separately retained ledger. The import command requires an explicit isolated-restore confirmation and replays deletions transactionally:

```bash
docker compose --profile tools -f deploy/compose.yaml run --rm -T --no-deps api \
  flask --app givvi import-deletion-ledger --confirm-isolated-restore < "$GIVVI_LEDGER_FILE"
```

Do not point this command at the live database. Verify deleted profiles, credentials, wishlist data, queued personal messages, neutral roster labels, and retained assignments before reopening access. The replay is idempotent. The separately retained ledger contains personal identifiers and timestamps; protect it like sensitive production data.

## Application Rollback

Keep the previous immutable API and web image tags available. If application behavior must be rolled back, restore those tags in the deployment environment and recreate the services. First verify that the previous application revision is compatible with the database schema after the migration. Prefer a forward corrective release if it is not. Do not assume a schema downgrade can restore deleted data or make a migration backward-compatible; use the tested isolated recovery procedure for database recovery.

## Current Limitations

The local snapshot-restore and previous-application compatibility rehearsal passed, but managed backup restoration and off-site deletion-ledger retention are not configured here. The production API/web HTTPS smoke has not passed in this environment. Provider-specific database roles/TLS, SMTP delivery, external alert delivery, manual accessibility and full acceptance review, and a closed-group pilot remain release gates. No production deployment or release has been performed.