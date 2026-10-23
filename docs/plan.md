# GIVVI Incremental Project Plan

## Purpose and Authority

Deliver the v1 requirements in [spec.md](spec.md) through small, demonstrable increments. [adr.md](adr.md) records the proposed implementation decisions, alternatives, patterns, and operational strategies. The spec governs product scope; an ADR does not override it.

This is a backlog, not a fixed-date schedule. Phase order expresses dependencies, not sprint duration. Phase 0 is approved; Phase 1 implementation is ready for review with the MVP immediate-signup change. Later phases require user verification of the preceding phase before work begins.

## Implementation Principles

- Build vertical slices: database changes, backend behavior, UI, authorization, and tests together.
- Keep the application a modular monolith; introduce abstractions only when a concrete boundary benefits from them.
- Start each task with a failing behavior check where practical, implement the smallest working change, and validate it before expanding scope.
- Enforce invariants on the server and in PostgreSQL, not only through disabled UI controls.
- Deliver English and Polish strings alongside features rather than translating at the end.
- Keep commits reviewable and migrations reversible or explicitly document irreversible changes.
- Pin dependencies, use existing libraries for security primitives, and follow the repository's Python rules.
- Record new architectural decisions and deviations in the ADR document before depending on them.
- Do not implement reservations, conversion, exclusions, push notifications, payments, or other deferred scope.

## Agile Workflow

1. Refine the next slice into user stories with observable acceptance criteria and dependencies.
2. Split work until each task can normally be completed and reviewed in one or two working days. Time-box uncertain work as a research spike with a written outcome.
3. Pull the highest-priority ready task; limit work in progress and finish a slice before starting another.
4. Demo the working flow at the end of each increment. Gather feedback and reorder remaining tasks without bypassing privacy or correctness gates.
5. Review failures, delivery friction, and ADR assumptions in retrospectives. Estimate only refined tasks; do not invent release dates from this document.

### Definition of Ready

- User outcome and spec requirement are identified.
- Dependencies and permission rules are understood.
- Success, failure, and concurrency cases are listed where relevant.
- Unresolved product behavior is settled or isolated behind a non-blocking task.

### Definition of Done

- The slice works end to end, including loading, empty, validation, permission, and failure states.
- Relevant unit, API, PostgreSQL integration, and browser tests pass.
- Backend lint/import checks and frontend lint/type/build checks pass.
- English and Polish text, keyboard access, and mobile layout are verified.
- Sensitive fields are absent from unauthorized responses, logs, and telemetry.
- Migrations, configuration, operating notes, and ADR changes are documented.
- Acceptance criteria are demonstrated in a reviewable environment.

## Phase 0: Resolve Contracts and Bootstrap

**Outcome:** A runnable foundation and agreed contracts. No speculative feature framework.

### Step 0.1: Close specification edge cases

- [x] P0.1a: Confirm what an invite holder may see before claiming. Recommend a minimal claim screen containing roster names and availability, but no wishlists, private event details, or assignments.
- [x] P0.1b: Confirm deletion eligibility after drawing has been enabled and subsequently reset. Recommend tracking whether drawing has ever been enabled and preventing permanent deletion thereafter.
- [x] P0.1c: Confirm account deletion for the sole admin and for active exchanges. Recommend requiring admin transfer or cancellation before admin deletion; preserve participant references as tombstones without reassigning recipients.
- [x] P0.1d: Clarify that archiving freezes event operations, not the user's global wishlist; decide whether already revealed recipients remain readable in archived/cancelled events. Recommend retaining previously revealed access without allowing new reveals.
- [x] P0.1e: Define supported gift currencies, price precision/ranges, input size limits, invite lifetime, and session/token lifetimes. Recommend EUR/PLN for gift prices, nonnegative decimal values, and bounded configurable limits.
- [x] P0.1f: Confirm whether deleting a profile also requires anonymizing historical roster names, and document retention and backup deletion expectations. Do not label retained personal names as anonymous.

**Acceptance:** Decisions are recorded in the spec or an approved clarification; dependent tasks do not silently pick conflicting behavior.

The user approved all six clarifications; exact limits and retention rules are recorded in spec section 14. Approval of these contracts does not mean their later-phase functionality is already implemented.

### Step 0.2: Establish development and CI

- [x] P0.2a: Create the `givvi` Python package, Flask application factory, environment configuration, `.venv` instructions, and fixed-version dependency files.
- [x] P0.2b: Initialize Vue with TypeScript, Vite, Router, Tailwind, and internationalization. Pin dependencies with a lockfile.
- [x] P0.2c: Add local Docker services for PostgreSQL and a development email inbox; provide placeholder configuration without credentials.
- [x] P0.2d: Add pytest fixtures under root `tests/`, frontend component tests, and Playwright browser tests.
- [x] P0.2e: Add CI for flake8, GOOGLE-profile isort, frontend checks, builds, and PostgreSQL integration tests. Add migration smoke tests as migrations appear.
- [x] P0.2f: Demonstrate a frontend request to a minimal backend readiness endpoint.

**Acceptance:** A documented clean checkout can run locally and CI validates the skeleton. Dependencies: P0.1 only where contracts affect scaffolding.

### Phase 0 Verification Checkpoint

Local checks passed on 2026-10-07: six backend unit tests, one real PostgreSQL integration test, five Vue component tests, and four desktop/mobile Playwright checks using the version-matched Docker browser runtime. Python lint/import checks, frontend lint/type/build checks, and documentation whitespace checks passed. Desktop/mobile screenshots were inspected.

The CI workflow is configured; a hosted GitHub Actions run has not been executed in this session. At the Phase 0 checkpoint, the app contained only a service-status screen. Phase 1 adds accounts and migration checks; event functionality remains deferred.

- [x] User verifies Phase 0 using the [README review steps](../README.md#phase-0-review).
- [x] User authorizes beginning Phase 1.

## Phase 1: Accounts and Localized App Shell

**Outcome:** A user can securely authenticate and navigate the bilingual application. Depends on Phase 0.

### Step 1.1: Registration and Immediate Login

- [x] P1.1a: Add user, session, one-time token, wishlist ownership, and email outbox migrations with uniqueness constraints.
- [x] P1.1b: Implement normalized email lookup, password hashing, and atomic creation of the user, one wishlist, and an authenticated session.
- [x] P1.1c: Implement expiring, single-use password-reset/email-change tokens and localized email templates. Do not issue signup verification tokens or emails.
- [x] P1.1d: Build registration with immediate dashboard navigation and generic duplicate-registration failure; retain email-change confirmation separately.
- [x] P1.1e: Test automatic login, session rotation, duplicate-registration safety, transaction rollback, no signup email, retained token expiry/replay, provider failure, and English fallback.

### Step 1.2: Sessions and recovery

- [x] P1.2a: Implement opaque server-side sessions, secure cookies, CSRF protection, logout, and authenticated-account guards without a registration-verification gate.
- [x] P1.2b: Add login throttling and generic invalid-credential responses.
- [x] P1.2c: Add password reset request/consume flows; revoke sessions after reset and rotate identifiers on authentication.
- [x] P1.2d: Implement login and recovery pages with safe return-to navigation after an invitation.
- [x] P1.2e: Test session expiry, revocation, CSRF rejection, open-redirect rejection, and reset-token replay.

### Step 1.3: Profile and navigation

- [x] P1.3a: Build Events, Wishlist, and Profile routes with mobile bottom navigation and dedicated pages.
- [x] P1.3b: Add name/language editing and password change with reauthentication. Treat email changes as pending until verified.
- [x] P1.3c: Add English and Polish catalogs, locale formatting, English fallback, and missing-translation checks.
- [x] P1.3d: Verify keyboard navigation, form labels, focus behavior, narrow viewports, and long translated labels.

**Acceptance:** Registration immediately signs the user in without email verification. Logout, recovery, and email-change confirmation work in both languages; protected APIs reject unauthenticated users.

### Phase 1 Verification Checkpoint

Verified locally on 2026-10-07: 33 backend unit tests, five PostgreSQL integration tests, 16 frontend tests, and eight desktop/mobile browser checks passed. Python lint/import checks, frontend lint/type/build checks, and whitespace validation passed. Browser journeys verify immediate signup without email, profile editing, keyboard focus, logout, email-change confirmation, and password recovery in both languages. PostgreSQL checks cover migration drift, competing registration/reset requests, and upgrading an existing unverified account without losing credentials.

The local database is migrated and the API, frontend, and Mailpit worker are running for review. Hosted GitHub Actions has not been run in this session. Events and Wishlist are navigation shells only; management features remain in later phases.

- [x] User verifies Phase 1 using the [README review steps](../README.md#phase-1-review).
- [x] User authorizes beginning Phase 2.

## Phase 2: Organizer-Managed Events

**Outcome:** An organizer can create an event and prepare its roster. Depends on Phase 1.

### Step 2.1: Event creation and listing

- [x] P2.1a: Add event and participant migrations, one-admin ownership, lifecycle fields, time zone, date/time, and decimal budget.
- [x] P2.1b: Implement create/read/edit endpoints using shared authorization and domain validation.
- [x] P2.1c: Create event form and dashboard; apply EUR/PLN defaults once at creation without later language-driven changes.
- [x] P2.1d: List owned/joined events with pagination and exchange-date grouping in each event's time zone.
- [x] P2.1e: Test date boundaries, daylight-saving behavior, missing required fields, invalid currency/budget, and cross-event access denial.

### Step 2.2: Roster preparation

- [x] P2.2a: Implement admin-only roster add, rename, and remove while drawing is disabled. Claim correction follows in P3.2c, after claims exist.
- [x] P2.2b: Build roster editing and pending-status views; do not automatically enroll the organizer.
- [x] P2.2c: Add constraints for one user per event entry and one claimed entry per user per event.
- [x] P2.2d: Test non-admin attempts, duplicate claims, organizer participation, and rejected mutations of read-only events.

**Acceptance:** The admin can prepare an event and roster; other accounts cannot inspect or mutate it without authorized access.

### Phase 2 Verification Checkpoint

Verified locally on 2026-10-16: event creation, editing, pagination, local-date grouping, DST validation, roster management, authorization, and database claim uniqueness pass their unit and PostgreSQL checks. English and Polish browser journeys pass on desktop and mobile. Phase 2 Python files pass lint/import checks; frontend tests, lint, typecheck, and build pass. Repository-wide flake8 still reports a continuation-indentation warning in the pre-existing `givvi/mail.py` edit. The hosted GitHub Actions workflow has not been run.

The Events view is ready for user review. Invitations, self-service claims, wishlists, and drawing remain later-phase functionality. Claim correction is scheduled with P3.2c because it requires an existing claim.

- [x] User verifies Phase 2 using the [README review steps](../README.md#phase-2-review).
- [x] User authorizes beginning Phase 3.

## Phase 3: Invitations and Self-Service Claims

**Outcome:** A closed group can join without admin claim approval. Depends on Phase 2 and email delivery from Phase 1.

### Step 3.1: Invitation entry

- [x] P3.1a: Add hashed event-link secrets, revocation/regeneration, and admin email invitation endpoints.
- [x] P3.1b: Implement a limited claim-entry response consistent with P0.1a; preserve access through registration/login without leaking tokens.
- [x] P3.1c: Allow accepted participants to share the current link; restrict email invitation sending to the admin.
- [x] P3.1d: Localize invitation emails using the recipient's preference or English when unknown.
- [x] P3.1e: Test revoked links, token leakage prevention, invalid return URLs, and rate limits.

### Step 3.2: Atomic claims

- [x] P3.2a: Implement self-service claim transactions with event locking and uniqueness conflict handling.
- [x] P3.2b: Build claim selection and conflict recovery; users cannot create new entries through a link.
- [x] P3.2c: Allow admin correction of an existing claim while drawing is disabled; refresh roster status after claims/corrections and reject claims while drawing is enabled or the event is read-only.
- [x] P3.2d: Run PostgreSQL tests for competing claims, the drawing-enabled guard, and claim versus roster removal. The concurrent claim-versus-draw transition test depends on the drawing operation in P5.1b and is required there.

**Acceptance:** Only one concurrent claimant succeeds; a joined participant sees event details, while an invite holder does not gain unrestricted access.

### Phase 3 Verification Checkpoint

Verified locally on 2026-10-20: 57 backend unit tests and nine PostgreSQL integration tests pass, including migration drift, competing claims, one-account uniqueness across sessions, claim versus roster removal, and drawing-enabled claim rejection. The race against draw generation remains a P5.1b/P5.1e gate because drawing does not yet exist. All 27 frontend component/API tests, typecheck, and production build pass. The full 16-test desktop/mobile Playwright suite passed, and all four bilingual invite journeys passed again after the final conflict-recovery change. Frontend ESLint exits successfully with Vue template-formatting warnings in the compact Event Detail and Events views; it reports no errors. The hosted GitHub Actions workflow has not been run.

The invite-to-claim flow is ready for user review. Wishlists and drawing remain unimplemented.

## Phase 4: Wishlist Management and Event Viewing

**Outcome:** Users maintain one reusable prioritized wishlist. Depends on Phase 1 for ownership and Phase 3 for event visibility.

### Step 4.1: Owner gift management

- [x] P4.1a: Add gift fields, explicit price currency, stable ordering, constraints, and migrations.
- [x] P4.1b: Implement owner-only gift CRUD and atomic order updates, rejecting stale writes and duplicate/missing IDs.
- [x] P4.1c: Build gift list/edit pages, unknown-price states, empty states, and keyboard-accessible reorder controls.
- [x] P4.1d: Validate HTTP/HTTPS links without fetching them server-side; render descriptions as escaped text.
- [x] P4.1e: Test ownership denial, precision/ranges, deletion, ordering, malformed links, and concurrent updates.

### Step 4.2: Event-context wishlist access

- [x] P4.2a: Add member-authorized read projections exposing roster names rather than private account information.
- [x] P4.2b: Add participant wishlist pages and navigation back to the event.
- [x] P4.2c: Highlight over-budget items only for matching currencies and known budget/price; keep unknown and mismatched cases neutral.
- [x] P4.2d: Test membership revocation, no editing by viewers, all comparison cases, and absence of reservation controls.

**Acceptance:** Wishlist ownership and event access are enforced server-side; priority and budget display match the spec in both languages.

### Phase 4 Verification Checkpoint

Verified locally on 2026-10-20: 64 backend unit/API tests and 11 PostgreSQL integration tests pass, including migration upgrade/downgrade, database gift constraints, concurrent stale reorder rejection, and membership revocation. Frontend tests, lint, typecheck, and production build pass. Targeted Playwright journeys pass for owner gift management and event-member wishlist viewing in English and Polish on desktop and mobile; the account lifecycle journey with gift creation passes in English and Polish on desktop. Screenshots were inspected for both wishlist contexts. Python files changed in this phase pass flake8 and GOOGLE-profile isort. Hosted GitHub Actions has not been run.

The Phase 4 implementation is ready for user review at the local review URL. Phase 5 remains blocked on that review and separate authorization.

- [ ] User verifies Phase 4 using the [README review steps](../README.md#phase-4-review).
- [ ] User authorizes beginning Phase 5.

## Phase 5: Private Assignment and Reveal

**Outcome:** A complete Secret Santa exchange works end to end. Depends on Phase 3; wishlist navigation integrates Phase 4.

### Step 5.1: Atomic assignment generation

- [ ] P5.1a: Add assignment/generation records, unique giver/recipient constraints, no-self checks, and reveal timestamps.
- [ ] P5.1b: Implement enable-drawing under an event lock; validate three or more claimed entries and reject unclaimed entries.
- [ ] P5.1c: Generate an unbiased shuffled permutation using secure randomness, rejecting self-pairings; validate the complete result before committing.
- [ ] P5.1d: Lock roster and claims while enabled; return status only, never the assignment mapping.
- [ ] P5.1e: Test invariants across roster sizes and seeded test randomness, rollback, duplicate enable requests, and concurrent claims/roster changes against drawing.

### Step 5.2: Reveal and reset

- [ ] P5.2a: Implement a current-user-only reveal endpoint with event locking and idempotent repeat behavior.
- [ ] P5.2b: Build disabled/available/revealed UI states and a brief reveal animation honoring reduced-motion preferences.
- [ ] P5.2c: Add explicit reset confirmation; clear assignments only if no reveal exists and keep drawing history for deletion rules.
- [ ] P5.2d: Expose reveal status to the admin without recipient identities in any response or log.
- [ ] P5.2e: Test reveal versus reset/cancellation races, repeat requests, admin recipient-access denial, and disabled/reset states.

**Acceptance:** Every participant has one non-self recipient; no admin or other participant can inspect their mapping; the first reveal irrevocably blocks reset.

## Phase 6: Lifecycle and Account Cleanup

**Outcome:** Changes of plans and account departure have safe, explicit outcomes. Depends on Phase 5 and P0.1 clarifications.

### Step 6.1: Event lifecycle

- [ ] P6.1a: Implement archive/unarchive, cancellation, and permanent deletion rules using centralized state guards.
- [ ] P6.1b: Implement admin transfer as a single transaction to an existing participant.
- [ ] P6.1c: Build confirmation pages/controls and read-only cancelled/archived views; preserve date grouping independently.
- [ ] P6.1d: Test every mutation against archived/cancelled states, concurrent transfer, post-reset deletion eligibility, and retained reveal access.

### Step 6.2: Account deletion

- [ ] P6.2a: Implement reauthenticated deletion and admin handover/cancellation requirements established in P0.1c.
- [ ] P6.2b: Delete profile, wishlist, sessions, tokens, and queued personal payloads; anonymize retained identity references without changing assignments.
- [ ] P6.2c: Build deletion confirmation and neutral deleted-user views.
- [ ] P6.2d: Test deletion before/after draw, retained recipient references, private data removal, and old-session rejection.
- [ ] P6.2e: Document backup expiry and the distinction between logical deletion and removal from retained backups.

**Acceptance:** Read-only boundaries, transfer, and deletion work without reassignment or unintended disclosure.

## Phase 7: Operational Readiness and Release

**Outcome:** A deployable, observable, recoverable v1. Operational safeguards from earlier phases remain mandatory.

### Step 7.1: Reliable delivery and refresh

- [ ] P7.1a: Complete outbox retry/backoff, failed-delivery alerts, bounded retention, and worker recovery tests.
- [ ] P7.1b: Add visibility-aware polling, conditional requests, backoff, stale-response handling, and cache invalidation after mutations.
- [ ] P7.1c: Measure query counts, roster/wishlist payloads, and contention; add evidence-based indexes and fix N+1 queries.
- [ ] P7.1d: Run load tests with representative small-group data and concurrent claims/reveals. Record baseline latency, error rate, and capacity before setting release thresholds.

### Step 7.2: Deployment and security gates

- [ ] P7.2a: Build production Docker images, same-origin HTTPS routing, production WSGI configuration, non-root processes, and managed PostgreSQL configuration.
- [ ] P7.2b: Document secrets, migrations, release/rollback, worker startup, readiness, backup schedules, and restore procedure.
- [ ] P7.2c: Add dependency/image scanning and verify CSP, CSRF, cookie settings, rate limits, least-privilege credentials, and log redaction.
- [ ] P7.2d: Verify production prohibits debug mode and protects metrics; exercise email outage, database outage, and worker restart recovery.
- [ ] P7.2e: Restore a backup into an isolated environment and rehearse an application rollback compatible with the deployed schema.

### Step 7.3: Release review

- [ ] P7.3a: Run full Playwright scenarios in English and Polish on mobile/desktop, including invite-to-reveal and cancellation.
- [ ] P7.3b: Review accessibility, missing translations, account privacy, and all spec acceptance criteria.
- [ ] P7.3c: Publish operating instructions and known limitations; confirm deferred features remain absent.
- [ ] P7.3d: Pilot with a small closed group, triage defects, and release only after correctness/security gates pass.

**Acceptance:** CI passes, sensitive-data checks pass, backup restoration is demonstrated, and all v1 acceptance criteria have fresh evidence.

## Requirement Coverage

| Spec acceptance area | Delivery tasks | Primary evidence |
| --- | --- | --- |
| Register with immediate login, reset, profile, email change | P1.1-P1.3 | API and bilingual browser flows |
| Create event, roster, email/link invite | P2.1-P3.1 | Organizer-to-invitee scenario |
| Unique claims and authorized access | P3.2 | PostgreSQL race tests and access matrix |
| Drawing eligibility | P5.1 | Invalid-roster API cases |
| One-to-one, no-self assignment | P5.1 | Algorithm invariants and DB constraints |
| Private reveal, no admin inspection | P5.2 | Response, log, and authorization tests |
| Reset blocked after reveal, cancellation | P5.2, P6.1 | Race and lifecycle tests |
| Wishlist CRUD, priority, viewing | P4.1-P4.2 | Owner/viewer scenarios |
| Matching-currency budget highlight | P4.2 | Parameterized currency/price cases |
| Archived/cancelled read-only, past editable | P6.1 | State/mutation matrix |
| English/Polish interface and email | P1-P7 | Translation checks and email/browser tests |
| Mobile and desktop core flows | P1.3, P7.3 | Responsive Playwright checks |
| Account deletion and privacy | P6.2 | Anonymization and revocation tests |

## Backlog After V1

Reassess only after launch feedback: globally coordinated hidden gift reservations/purchases, custom exclusions, repeat-year pairing history, reminder delivery, additional languages/currencies, PWA/native support, and scale-driven infrastructure. Each requires a new product decision and ADR; none is an implicit v1 dependency.