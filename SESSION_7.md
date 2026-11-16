# Session 7: Phase 7 Operational Readiness

**Date:** 2026-10-28  
**Scope:** Implement and locally verify Phase 7 work authorized by the user. This session did not deploy or release the application.

## Initial prompt

Start Implemening the planned functionality based on the project specification and development plan in #file:plan.md . Follow best practices for coding, testing, and documentation to ensure a high-quality implementation.

Execute tasks from plan systematically, respecting dependencies and test-driven development.

Let me verify each phase

I am authorizing to proceed with phase 7

## Work Completed

- Hardened transactional email delivery with bounded exponential retry and jitter, expired-lease recovery, a five-attempt ceiling, terminal-failure logging, and seven-day retention for completed/failed rows. Added focused retry, lease, retention, privacy, and recovery tests.
- Added conditional ETags for authorized, non-sensitive GET projections, visibility-aware client polling with cancellation/backoff, stale-response guards, and cache invalidation after mutations. Previously revealed assignments can be read without causing a polling mutation loop; explicit reveal remains a POST.
- Batched event roster reads to remove the event-list N+1 query. The 10-event listing went from 15 queries to 6. Added query-count and PostgreSQL query-plan/load coverage.
- Added production configuration safeguards, mounted secret-file support, bounded PostgreSQL connection/statement/lock timeouts, redacted request timing logs, security headers, conditional validators, and token-protected aggregate outbox metrics.
- Added deletion-ledger CSV export and explicitly confirmed import/replay commands. Added an isolated PostgreSQL snapshot-restore and deletion-replay rehearsal, including a compatibility read smoke test against the previous application revision.
- Added production API and web container packaging, hardened Compose services, same-origin Caddy HTTPS routing, and CI checks for dependency audits, production image builds/scans, non-root images, and Compose/Caddy configuration. CI checks out history and supplies a rollback revision for the integration rehearsal.
- Resolved web-image scanner findings by building Caddy 2.11.7 with Go 1.27.3 and patched Go module versions rather than suppressing findings.
- Added a bilingual browser journey verifying polling observes external claims without overwriting an unsaved edit.
- Added [docs/operations.md](docs/operations.md) with production prerequisites, secrets, release/migration commands, health and worker checks, backup/deletion-ledger handling, restore, and rollback guidance. Updated README status and Phase 7 task evidence in [docs/plan.md](docs/plan.md).

## Local Verification Evidence

- Final local verification on 2026-10-29: 114 backend unit/API tests and 22 PostgreSQL integration tests passed. Python flake8 and isort passed; all 42 frontend tests, the ESLint error gate, TypeScript typecheck, and production frontend build passed. Documentation whitespace checks passed.
- The 2026-10-28 session verification also recorded 40 bilingual desktop/mobile Playwright journeys, dependency audits, production image scans, query/load checks, and an isolated restore/replay plus previous-revision compatibility check. Those checks were not rerun on 2026-10-29.
- PostgreSQL integration suite: 22 passed, including worker lease/restart behavior, concurrent group activity, and isolated encrypted snapshot restore plus deletion-ledger replay. The recovery rehearsal reported about 2.95 seconds for restore and compatibility checks against revision `a44b1dd58d804e191abc40beef6c22f43fce68c3`.
- Frontend: 42 Vitest tests passed and TypeScript typecheck passed.
- Browser suite: 40 Playwright journeys passed in English and Polish, desktop and mobile.
- Python flake8/isort checks passed after the backend/test changes. Local installed-environment pip-audit and npm audit were clean.
- Trivy found no fixable HIGH/CRITICAL vulnerabilities in either the API image or the rebuilt web image. Caddy configuration validated. Production Compose configuration and CI workflow YAML parsed/validated locally.
- A small synthetic PostgreSQL workload (12-person group, 4 claim workers, 96 reads) had zero errors. Measured p95 values were 409.27 ms for claims, 266.22 ms for reveals, and 183.7 ms for reads; maximum observed payloads were 1,357, 79, and 3,123 bytes respectively. These are local in-process baselines, not production capacity or SLO guarantees.

## Remaining Work and Release Gates

- The API/web production-container HTTPS smoke remains **unverified**. The first attempt used `givvi-smoke.test`; Caddy requested a public ACME certificate and received HTTP 400 because `.test` is not a public suffix. A follow-up using `localhost` had TLS connection resets followed by HTTP 404. The source of that 404 was not established, so do not claim end-to-end HTTPS success.
- Operating instructions and README/plan status updates are now present. The plan checks off only work with local evidence and lists the remaining blockers.
- Hosted GitHub Actions has not run. Browser screenshots/manual keyboard and accessibility review, and full specification acceptance review also remain outstanding.
- Production provider credentials, verified database TLS and least-privilege role checks, SMTP delivery, external alert receiver, automated off-site backup/deletion-ledger retention, and managed restore verification are not configured here.
- Browser screenshots/manual keyboard and accessibility review, full spec-acceptance review, and closed-group pilot remain outstanding. User review/approval and the release decision remain explicit gates.

The local review servers were left running at `http://127.0.0.1:5174` (frontend; API on port 5001). No commit, deployment, or release was made.
