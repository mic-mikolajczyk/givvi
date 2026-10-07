# Architecture Decision Records

## Status and Scope

These records describe the **target implementation**, not a claim that every strategy exists in code. The product authority is [spec.md](spec.md); delivery tasks are in [plan.md](plan.md). Phase 0 implements the application factory, configuration, database connectivity, frontend routing/localization, and test infrastructure. Remaining records are planning defaults until their delivery phase. Phase 0 product clarifications are approved and recorded in spec section 14.

Each record states context, decision/pattern, rationale and alternatives, implementation, and verification. Update or supersede a record when evidence changes; do not silently introduce another strategy.

## ADR-001: Modular Monolith and Application Factory

**Context:** A small-group product needs maintainability without distributed-system overhead.

**Decision/pattern:** Use one Flask API and a Vue client. Organize backend capabilities into accounts, events, invitations, wishlists, and assignments. Use a Flask application factory and dependency injection through explicit service construction/configuration.

**Rationale/alternatives:** A modular monolith keeps transactions local and deployments simple. Microservices would introduce network failures and duplicated authorization; a single unstructured module would couple unrelated behavior.

**Implementation:** Keep Python code in `givvi`, isolated unit tests under mirrored root `tests/`, and frontend code in a separate frontend directory. Inject clock, randomness, email adapter, and transaction/session dependencies where they vary or need controlled tests. Prefer composition and functions over deep inheritance. Do not build a general dependency-injection framework.

**Verification:** Independent app instances use isolated test configuration; domain behavior can be exercised without starting HTTP servers or contacting providers.

## ADR-002: MVC, Service Layer, and Explicit Projections

**Context:** HTTP handlers must not become the only place where business rules live or leak ORM records.

**Decision/pattern:** Use MVC separation: models represent persisted/domain data, controllers handle HTTP validation and identity, response serializers are API views, and Vue renders the user interface. Application services own use cases and transactions. Authorization policies and state guards are reusable explicit functions.

**Rationale/alternatives:** This separates transport from decisions and makes rules testable. Generic repositories and a full CQRS framework add no demonstrated value; direct ORM usage inside narrowly scoped services is sufficient. Read projections are a data-minimization technique, not a separate CQRS deployment.

**Implementation:** Controllers call services and return allowlisted response objects. Never serialize entire user or assignment models. Provide distinct event-status and own-recipient projections. Vue uses feature components and small composables for shared session, API, and polling behavior; avoid a global store unless shared state actually needs one.

**Verification:** Service tests assert outcomes; API tests assert status, schema, and absence of private fields across roles.

## ADR-003: PostgreSQL, Migrations, and Relational Invariants

**Context:** Claims, assignments, ordering, and admin ownership require reliable consistency.

**Decision/strategy:** Use SQLAlchemy with Alembic migrations and PostgreSQL as the authoritative database. Use explicit relational constraints alongside domain validation.

**Rationale/alternatives:** ORM mapping and migration tooling avoid handwritten persistence scaffolding. SQLite may support lightweight tests but cannot establish PostgreSQL locking or constraint semantics.

**Implementation:** Model users, sessions, tokens, events, roster entries, draw generations, assignments, gifts, and outbox messages. Use an event admin foreign key for single ownership; unique wishlist ownership; unique `(event_id, user_id)` for non-null claims; unique giver and recipient per draw generation; no-self checks; and foreign keys ensuring assignments refer to the correct event roster. Use tombstoned roster references rather than deleting assignment identities. Store money as decimal/numeric, require currency with a known price, and represent unknown price as null.

**Verification:** Run migrations from an empty PostgreSQL database and upgrade fixtures. Assert constraint violations and referential integrity, not just ORM validation. Production-equivalent integration tests cannot be replaced by SQLite tests.

## ADR-004: State Guards and Transactional Concurrency

**Context:** Reveal versus reset and competing claims can violate product rules if implemented as separate read/write operations.

**Decision/pattern:** Represent lifecycle explicitly and apply a lightweight state-machine strategy through named transitions and guard functions. Treat event mutations as a unit of work, using a consistent event-row lock before reading mutable event state.

**Rationale/alternatives:** In-process locks fail across workers. Optimistic UI checks alone cannot protect server invariants. Database transactions and constraints are sufficient without distributed locks.

**Implementation:** Keep exchange-date grouping separate from drawing, archive, and cancellation state. Lock the event first for claims, roster changes, enable/reset/reveal, cancellation, transfer, and deletion; then validate and mutate in one transaction. Reveal is idempotent; repeated enable cannot regenerate an active draw. Reset checks reveal existence under the same lock. Use version checks for event-detail and wishlist-order edits to prevent lost updates. Keep external network calls outside transactions and define a consistent lock order for account cleanup.

**Verification:** Use independent PostgreSQL connections to force racing operations. Prove no partial draw, double claim, reset-after-reveal, or multiple-admin outcome is possible. Return a recoverable conflict rather than hiding a race.

## ADR-005: Unbiased Secret Santa Generation

**Context:** Every claimed participant must give and receive exactly once without self-pairing; custom exclusions are deferred.

**Decision/strategy:** Use secure standard-library randomness to shuffle all recipients uniformly, rejecting permutations with fixed points. Validate the completed derangement before persistence.

**Rationale/alternatives:** Rejection sampling is simple and yields uniform valid permutations for the small rosters in scope; its expected trial count stays small. A shuffled cycle would exclude valid multi-cycle assignments and change the distribution. Do not promise fresh pairings on reset or invent a general constraint solver.

**Implementation:** Inject randomness in tests, never use predictable production seeds, and enforce a bounded failure safeguard that aborts without partial assignments rather than introducing a biased fallback. Commit all assignments with drawing state under ADR-004. Reveal loads only the requesting participant's assignment; frontend animation never computes or downloads the complete mapping.

**Verification:** Parameterized invariants across roster sizes, deterministic controlled cases, failure rollback, and recipient-response privacy. Avoid flaky statistical tests as a correctness gate.

## ADR-006: Same-Origin Sessions and Credential Security

**Context:** A browser-first application needs revocable authentication without exposing long-lived credentials to JavaScript.

**Decision/strategy:** Deploy frontend and API under one origin. Use random opaque session identifiers in HttpOnly cookies backed by PostgreSQL session records; use CSRF tokens for state-changing requests. Hash passwords with maintained Argon2id tooling.

**Rationale/alternatives:** Server sessions simplify logout/revocation and account deletion. Browser-local JWT storage increases credential exposure and complicates revocation. SameSite cookies are helpful but do not replace CSRF protection.

**Implementation:** Store session/token digests rather than raw secrets, rotate on login, expire sessions, and revoke after reset/deletion. Set Secure, HttpOnly, and SameSite=Lax in production; verify request origin and CSRF token. Use expiring single-use verification/reset tokens and reauthentication for sensitive changes. Verify new email before replacement. Never implement cryptographic primitives or password hashing manually.

**Verification:** Cookie settings, session fixation, expiration, reset replay, CSRF, logout, and unverified-user access tests. Protect secret configuration and prevent debug mode in production.

## ADR-007: Authorization, Invitations, and Data Minimization

**Context:** Link possession must not expose the event, and admin privileges must not reveal assignment recipients.

**Decision/strategy:** Deny by default with explicit ownership/membership policies at each service boundary. Invitation capability grants only the approved claim-entry view until membership is established.

**Rationale/alternatives:** UI hiding and guess-resistant IDs are not authorization. A broad admin serializer risks accidental assignment disclosure.

**Implementation:** Require verified accounts for protected operations. Allowlist event roster names and reveal status; exclude account names/emails and assignment mapping. Store invitation secret digests and rotate/revoke the capability; do not auto-claim entries from emailed addresses. Keep secrets out of query/access logs and referrers using redaction and Referrer-Policy. Use a dedicated current-user reveal route rather than an arbitrary participant-recipient lookup. Limit invitation attempts and recheck access on every request.

**Verification:** Build a role/action matrix for outsider, invite holder, member, owner, and admin. Test cross-event identifier substitution, revoked links, claim correction, and all response fields. The promise applies to app roles, not unrestricted database operators; document and tightly restrict infrastructure access.

## ADR-008: Input Safety, Abuse Controls, and Browser Defenses

**Context:** Descriptions, gift links, auth endpoints, and email sending are untrusted inputs and abuse surfaces.

**Decision/strategy:** Validate structured input server-side, escape text, and use defense in depth.

**Rationale/alternatives:** Client validation improves usability but is bypassable. Server-side link previews would add SSRF risk and are unnecessary in v1.

**Implementation:** Use schema validation, length/range limits, parameterized ORM queries, strict EUR/PLN event currency, and IANA time-zone validation. Permit HTTP/HTTPS gift URLs only; do not fetch external URLs. Use safe external-link attributes, a restrictive CSP, HTTPS/HSTS once HTTPS deployment is verified, and no permissive credentialed CORS. Apply maintained shared-storage rate limiting to login, registration, resets, resend, invitations, and claims; in-memory counters alone are not a production multi-worker guarantee. Use generic auth/recovery messages to reduce enumeration.

**Verification:** Invalid payload, XSS, scheme injection, open redirect, rate limit, and oversized request tests; check production headers and proxy trust configuration.

## ADR-009: Transactional Outbox and Email Adapter

**Context:** Verification, recovery, and invitations must survive email-provider outages without holding database locks.

**Decision/pattern:** Use the transactional outbox pattern and a small email-provider adapter. Store delivery intent with the business transaction; a separate worker sends committed messages.

**Rationale/alternatives:** Direct sends can succeed before a failed commit or disappear after one. A PostgreSQL outbox avoids needing a message broker for v1; a worker adds operations but provides recoverable delivery.

**Implementation:** Worker claims messages safely, sends with provider timeouts, tracks attempts, and retries transient failures with capped exponential backoff/jitter. Permanent failures become operator-visible. Use provider idempotency keys where supported; otherwise acknowledge possible duplicate delivery under at-least-once semantics. Encrypt temporary token-bearing payloads with a managed deployment secret and purge after delivery/expiry; never log bodies or tokens. Development uses a local inbox and integration tests use an adapter fake.

**Verification:** Transaction rollback queues nothing; worker crash/restart, provider timeouts, duplicate delivery, redaction, and payload expiry are tested. Templates support both languages and English fallback.

## ADR-010: Localization, Money, and Time

**Context:** Polish is a primary target language, but language is not the same thing as an event's currency or time zone.

**Decision/strategy:** Use Vue internationalization catalogs for UI and localized backend email templates. Store language, currency, and time zone separately.

**Rationale/alternatives:** Translating after implementation leaves inaccessible flows. Implicit currency conversion or language-driven changes to stored money would violate the spec.

**Implementation:** Default to English, support Polish, and use stable error codes translated by the client. Set event currency once from user language, then retain explicit selection. Use decimal arithmetic; compare prices only for equal currencies and known values. Keep exchange date as an event-local date, optional time separate, and technical timestamps in UTC. Render localized dates/numbers without changing stored values.

**Verification:** Catalog completeness, Polish email/browser flows, unknown-price display, equal/above/mismatched currency cases, and date boundaries including daylight-saving changes.

## ADR-011: API Errors, Recovery, and Logging

**Context:** Expected conflicts need actionable feedback; unexpected failures must be observable without disclosing private data.

**Decision/pattern:** Use typed domain errors mapped centrally to a consistent API error envelope. Use structured JSON logging and request correlation.

**Rationale/alternatives:** Scattered exception handlers yield inconsistent responses. Raw exceptions expose internals; swallowing them masks defects. Error reporting and user messaging have different audiences.

**Implementation:** Return `code`, safe `message`, allowlisted `field_errors`, and `request_id`. Map malformed input to 400, missing authentication to 401, disallowed operations to 403, inaccessible/missing resources to a consistent 404 policy, stale/state conflicts to 409, schema validation to 422, throttling to 429 with retry guidance, and dependency unavailability to 503. Unexpected exceptions produce a generic 500 and one redacted server-side stack trace. Roll back transactions before responding; translate known constraint violations rather than broadly treating all database errors as conflicts.

Frontend pages show loading/empty/error states, preserve user input, handle expired sessions, and refresh on conflicts. Retry safe reads and transient worker failures with bounds; do not blindly retry mutations or invalid credentials. A repeated reveal safely returns the existing result.

Log request ID, route template, status, duration, operation, and opaque identifiers only when needed. Log security/lifecycle audit actions separately from detailed diagnostics; never log passwords, session/invite/reset secrets, bodies, emails, wishlist content, or giver-recipient pairs. Do not record raw URLs with secret query parameters. Configure access-controlled retention and redact provider/database exception details. No silent exception handling; expected rejections use appropriate informational/warning levels rather than noisy stack traces.

**Verification:** Error-envelope contract tests, input preservation, transaction rollback, sensitive-value log scans, and trace correlation during simulated outages.

## ADR-012: Polling and Measured Performance

**Context:** Small groups need fresh state, not a push-event platform; unchecked polling and ORM loading can still overload the API.

**Decision/strategy:** Use visibility-aware polling and efficient bounded reads. Optimize from measurements, not speculative caches or sharding.

**Rationale/alternatives:** WebSockets add connection management and synchronization complexity. Shared caching of private event projections risks leakage and stale authorization.

**Implementation:** Poll active event pages at a configurable interval, pause in background, cancel obsolete requests, back off after errors, and immediately invalidate relevant client queries after mutations. Use conditional requests where useful, private/no-store caching for recipient and sensitive responses, and no shared sensitive-response cache. Paginate event/gift lists where needed, bound request payloads/rosters, eager-load only required relationships, and index membership, assignment lookup, ordered gifts, token/session expiry, and pending outbox access based on query plans. Keep transactions short and avoid provider calls under locks. Use deployment-sized database pools and request/statement timeouts.

**Verification:** Count queries to detect N+1 behavior; use PostgreSQL query plans and representative load tests. Measure p95 latency, error rates, lock waits, and polling load before agreeing numeric release budgets. Do not advertise unmeasured capacity.

## ADR-013: Account Deletion and Retained History

**Context:** Deleting an account must remove personal data without changing other participants' assignments.

**Decision/strategy:** Separate event roster references from live account identities and use anonymized tombstones for retained history.

**Rationale/alternatives:** Cascading deletion of assignments invalidates the exchange. Retaining a profile with a deleted flag does not meet the intended personal-data removal.

**Implementation:** After approved admin-departure handling, revoke sessions/tokens, remove wishlist/profile data, detach user references, and replace retained identity labels consistently. Remove pending personal email payloads. Preserve opaque participant/assignment references. Apply the approved policy to names that themselves contain personal data. Define backup expiration, retained audit data, and restore-time reapplication of deletion records; do not promise immediate physical deletion from all backups.

**Verification:** Deletion fixtures before and after drawing, admin handover scenarios, stale-token rejection, history integrity, and checks for retained identifying fields. Product ambiguities must be settled through plan step 0.1 before implementation.

## ADR-014: Risk-Based Testing and Continuous Delivery

**Context:** The largest risks involve access boundaries, cross-request races, and browser flows rather than raw line coverage.

**Decision/strategy:** Use a layered test strategy: focused domain tests, Flask API contracts, PostgreSQL transaction tests, Vue component tests, and a small set of Playwright journeys.

**Rationale/alternatives:** Mock-only tests cannot prove persistence or authorization behavior. Browser-only suites are slow and poor at forcing race conditions. A 100% coverage target encourages low-value tests.

**Implementation:** Follow pytest conditions/action/expectations and shared fixtures under root `tests/`. Mock external adapters, not the function under test. Use real PostgreSQL for locking, migrations, and constraints. Use controlled clocks/randomness for deterministic tests. Check EN/PL mobile/desktop journeys and reduced-motion accessibility. Run lint, type/build, tests, dependency checks, and migration checks in CI; require behavior evidence for each slice.

**Verification:** Every acceptance area has mapped checks in the plan. No skipped critical integration scenario can count as a completed release gate.

## ADR-015: Docker Deployment, Observability, and Recovery

**Context:** V1 needs dependable operation with a small operational footprint.

**Decision/strategy:** Use Docker-packaged frontend/API and outbox worker, same-origin HTTPS routing, and managed PostgreSQL. Defer Kubernetes and service decomposition.

**Rationale/alternatives:** Simple deployment reduces maintenance; production still requires an explicit migration, backup, and rollback process. Containers alone do not supply these guarantees.

**Implementation:** Use non-root containers, a production WSGI server, least-privilege database credentials, external secrets, pinned/scanned dependencies, and no debug mode. Run migrations as a controlled deployment step, not from every worker startup. Use expand/contract changes where rollback compatibility matters. Collect protected aggregate metrics for latency, failures, pool/lock pressure, outbox backlog, and delivery failures without sensitive labels. Separate liveness from dependency readiness; provider outage should not kill healthy API processes. Configure automated encrypted backups and test restoration in isolation.

**Verification:** Rehearse deployment/rollback, restore a backup, simulate database/email outages, and verify alerts and redaction. Record actual recovery objectives and capacity after rehearsal rather than asserting unsupported guarantees.

## ADR-016: Deliberate Scope Control

**Context:** The original idea includes functionality explicitly deferred during product refinement.

**Decision/strategy:** Keep v1 focused on the event-to-reveal loop and reusable wishlists. Use backlog prioritization rather than speculative plugin systems or dormant features.

**Rationale/alternatives:** Global reservations create cross-event privacy and concurrency requirements. Exclusions change assignment feasibility. Kubernetes, social login, payments, and push notifications add unrelated dependencies.

**Implementation:** Do not add reservation status, conversion, exclusions, notification center, or payment schemas/UI for v1. Existing module boundaries allow later extension without predicting its full design. Any future feature needs an approved spec change, dedicated acceptance criteria, and a new or superseding ADR.

**Verification:** Release review checks both included requirements and absence of deferred behavior. Update this record only when scope is deliberately revised.

## ADR-017: Phase 0 Foundation and Verification Checkpoint

**Status:** Implemented foundation; user review is required before Phase 1.

**Context:** The repository initially contained planning documents only. The first increment must prove the development toolchain and frontend-to-database path without pretending account or event features exist.

**Decision/strategy:** Expose separate `/api/health/live` and `/api/health/ready` endpoints. Readiness executes a database query and returns only `ready` or `unavailable`; liveness does not require PostgreSQL. Serve a minimal bilingual status view through Vite's same-origin development API proxy.

**Implementation:** Each Flask factory call creates an independent SQLAlchemy engine. Missing database configuration fails at startup; PostgreSQL connections use a three-second connection timeout. Readiness failure logs a constant warning without connection details, returns 503, and disables caching. The Vue view has loading, success, unavailable, and retry states, a bounded cancellable request, and English/Polish text. Use the maintained `@lucide/vue` package rather than its deprecated predecessor. Local PostgreSQL and Mailpit bind only to loopback with persistent database storage; example passwords are placeholders, never production credentials.

**Rationale/alternatives:** A process-only readiness check would hide database outages. A mock database cannot validate the integration path. Production WSGI, structured application errors/logging, authentication, migrations, and email delivery remain in their planned phases; the local Flask server is development-only.

**Verification:** Backend tests begin with a missing-package failure; component tests begin with missing-view/translation failures. PostgreSQL integration tests explicitly fail without their configured database, rather than silently skipping. Browser tests exercise actual readiness and error recovery on desktop/mobile. CI installs browser dependencies; hosts without those libraries can use the version-matched Playwright Docker image. Migration checks begin when Phase 1 introduces migrations.
