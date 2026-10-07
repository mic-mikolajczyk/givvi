# GIVVI Product Specification

## 1. Overview

GIVVI is an invite-only, responsive web application for organizing Secret Santa exchanges among families and friends. Organizers create events, define the participant roster, and enable a private one-to-one gift assignment. Users maintain one wishlist that event participants can view.

This document defines the first release (v1). Features listed as out of scope are not required for v1.

## 2. Product Goals

- Let an organizer create and manage a Secret Santa event with a confirmed roster.
- Let participants securely claim their event identity and view event information and wishlists.
- Generate valid Secret Santa assignments and reveal each privately to its recipient.
- Let users create and prioritize a wishlist that can be reused across events.
- Provide a usable experience on mobile and desktop browsers in English and Polish.

## 3. Users and Roles

### Account user

An account user signs in with a verified email address. Each user owns one wishlist and may participate in multiple events.

### Event admin

Each event has one admin. The creator becomes the initial admin. The admin manages event details, the participant roster, drawing, archive/cancellation, and admin transfer.

### Event participant

An event participant is a user who has claimed one roster entry. The event-specific roster name is shown to other participants; the account name and email remain private unless the user shares them.

An account may claim at most one roster entry in an event, and a roster entry may be claimed by at most one account.

## 4. V1 Scope

### Included

- Registration, login, email verification, password reset, and logout.
- English and Polish user interface and transactional email.
- Event creation, editing, roster management, invitations, and event dashboards.
- Self-service claims against pre-created roster entries.
- Secret Santa assignment generation and private participant reveal.
- Wishlist create, read, update, delete, and priority ordering.
- Event-scoped wishlist viewing and matching-currency budget highlighting.
- Event archival, unarchival, cancellation, and admin transfer.
- Responsive web interface for mobile and desktop browsers.

### Out of scope

- Native mobile apps or installable PWA support.
- Kubernetes deployment.
- Multiple event admins.
- Guest participants without accounts.
- Custom assignment exclusions or guarantees against repeated pairings across resets.
- Currency conversion.
- Global or event-scoped reservation and purchased markers.
- Reminder emails, an in-app notification center, and organizer-triggered reminder messages.
- Social sign-in, passwordless sign-in, and additional languages.

## 5. Account and Onboarding Requirements

- Users register and sign in using email and password.
- Email verification is required. Users can request a password reset by email.
- Transactional emails use the recipient's selected language; English is the fallback.
- The profile includes the user's name, email, and language preference. Users can update profile details, change their password, and log out.
- English is the default interface language. Polish is also supported in v1.
- Theme selection is not required for v1.

## 6. Event Requirements

### Creation and details

- Any signed-in user can create an event and becomes its admin.
- Event name and exchange date are required.
- Event time, location, description, and maximum gift budget are optional.
- The event's time zone is stored so its date and optional time are unambiguous.
- Event currency is either EUR or PLN. The initial currency defaults to EUR for an English-language user and PLN for a Polish-language user. The admin can change the event currency; changing language later does not change an existing event's currency.
- Only the admin can edit event details and manage roster entries.

### Event lifecycle and dashboard

- Events are grouped as upcoming, ongoing, or past based on the exchange date in the event's time zone. The exchange date is ongoing on that date, upcoming before it, and past after it.
- Past status does not make an event read-only. Archiving makes an event read-only for all participants. The admin may unarchive it.
- The dashboard shows the event details, roster, participant claim status, drawing status, and relevant pending states.
- A cancelled event remains visible to its participants as read-only with a clear cancelled status. No new assignments are generated or revealed after cancellation.
- The admin may permanently delete an event only before drawing is enabled. After drawing is enabled, the admin can cancel or archive it instead.
- The admin may transfer admin ownership to another event participant. Only one admin is active at a time.

### Roster, invitations, and claims

- The admin creates roster entries before inviting participants. Roster names are event-specific and do not need to match account names.
- Only the admin can create, rename, or remove roster entries. Roster editing is allowed only while drawing is disabled.
- The admin can send event invitations by email.
- Any accepted participant can share the active event link. The admin can revoke or regenerate that link.
- The link requires registration or login. It lets a user claim an existing unclaimed roster entry; it does not create roster entries.
- Users select an unclaimed roster entry themselves. Claims do not require admin approval.
- The admin can correct a mistaken claim before drawing is enabled.
- Drawing cannot be enabled while any roster entry is unclaimed. The admin must claim, correct, or remove those entries first.

## 7. Secret Santa Assignment

- Drawing is disabled by default.
- Drawing can be enabled only by the admin when at least three roster entries are claimed.
- Enabling drawing creates a complete one-to-one assignment. No participant is assigned to themselves, and every participant is assigned exactly one recipient.
- Assignments are generated once when drawing is enabled. Participants do not receive a new assignment by pressing the reveal control.
- Each participant can reveal only their own assigned recipient, and only after drawing is enabled. Before reveal, the dashboard indicates that drawing is available; after reveal, it shows the assigned recipient instead of the reveal control.
- The reveal may use a brief animation or delay, but assignment correctness and privacy must not depend on client-side behavior.
- The admin can see reveal status but cannot see assignment recipients.
- Resetting is an explicit admin action with a confirmation step. It is allowed only before any participant has revealed. Reset clears all assignments and permits roster changes. A new draw may produce the same pairings as a previous draw.
- Once any participant has revealed, the roster and assignments cannot be reset. If the exchange must stop, the admin cancels the event rather than reshuffling.

## 8. Wishlist Requirements

### Owner experience

- Each user has exactly one wishlist, managed from the wishlist view.
- A gift has a required name and optional description, price, currency, and link.
- If a gift has no price, it is explicitly displayed as unknown.
- Users can add, edit, and remove their gifts and reorder them to indicate priority.
- Gift links may point to an online shop or image.

### Participant experience

- A participant can view the wishlists of all participants in their event, including before assignment reveal.
- Participants cannot edit another user's wishlist.
- Gift prices retain their own currency. When viewing a wishlist in an event, a gift is highlighted as over budget only when both its price and the event budget have the same currency and the gift price exceeds the budget.
- No currency conversion is performed.
- V1 does not expose reserved or purchased status.

## 9. Primary Views and Navigation

- After login, users arrive at the main dashboard.
- Main navigation provides dedicated Events, Wishlist, and Profile views. On mobile, primary navigation is available at the bottom of the screen.
- The Events view groups events by upcoming, ongoing, and past and provides event creation.
- The event detail view shows event information, roster, claim/drawing status, and admin controls where applicable.
- Selecting a participant opens that participant's wishlist, with a clear route back to the event.
- The Wishlist view supports gift management and priority ordering.
- The Profile view supports personal details, language, password management, and logout.
- Primary navigation uses dedicated pages, not modal windows.

## 10. Notifications and Updates

- V1 sends transactional email for account verification, password reset, and event invitations.
- The admin may send event invitations by email; accepted participants may invite others by sharing the event link.
- Email invitations are localized using the recipient's selected language, falling back to English.
- The event dashboard communicates pending states such as unclaimed roster entries and unrevealed assignments.
- Changes are reflected through periodic refresh/polling and normal page navigation. Full real-time push updates are not required.

## 11. Privacy and Security Requirements

- Event details, roster membership, wishlists, and assignments are accessible only to signed-in users with the appropriate event membership or ownership.
- The system must enforce authorization on the server for every protected operation; hiding a control in the interface is not sufficient.
- Assignment recipients are visible only to the assigned participant. The event admin can see reveal status, not recipient identity.
- Account email addresses and account names are not disclosed to other event members by default.
- Invitation links must be revocable by the admin. A link cannot bypass account registration/login or create roster entries.
- Wishlist reservation and purchase data is not part of v1.
- On account deletion, remove the user's profile and wishlist and replace their identity in retained event history with a neutral deleted-user label. Preserve existing event assignments and do not disclose other participants' assignments.

## 12. Technical Direction

- Frontend: Vue.js and Tailwind CSS.
- Backend: Python and Flask.
- Primary database: PostgreSQL.
- Tests may use SQLite where appropriate.
- Container packaging: Docker. Kubernetes is deferred.
- The system should use a clear separation between frontend, backend API, and persistence, and be structured for maintainability and future growth.

## 13. Acceptance Criteria

- A user can register, verify their email, sign in, reset their password, and manage their profile.
- A user can create an event with the required name and date, add roster entries, and share or email invitations.
- Invitees can sign in or register, claim unique roster entries, and access only events they belong to.
- The admin cannot enable drawing with fewer than three claimed participants or with any unclaimed roster entry.
- A valid draw assigns every participant exactly one other participant, with no self-assignment or duplicate recipient.
- Only a participant can reveal their own assignment. The admin cannot inspect recipient identities through the application.
- An explicit reset is blocked after the first reveal; cancellation remains available to the admin.
- Users can manage and prioritize wishlist gifts. Event participants can view them without editing them.
- Over-budget highlighting is correct when gift and event currencies match and omitted when they differ.
- Archived and cancelled events are read-only; past status alone does not make an event read-only.
- English and Polish are available in the application and transactional email, with English as the fallback.
- Core flows work in supported mobile and desktop browsers.

## 14. Approved Phase 0 Clarifications

The following defaults were approved before implementation. They refine the requirements above and are acceptance criteria for the relevant delivery phases.

- Before claiming an entry, a signed-in invite holder can see only roster names and entry availability. Private event details, wishlists, and assignments remain inaccessible until membership is established.
- Permanent event deletion is allowed only if drawing has never been enabled. Resetting does not restore deletion eligibility.
- The organizer is not automatically a participant and must claim a roster entry to join the exchange.
- Deleting an account requires transferring its admin ownership or cancelling affected events first. Existing assignments retain anonymized participant references and are never reassigned as a side effect of deletion.
- Archiving freezes event operations, not users' global wishlists. Previously revealed recipients remain readable in archived and cancelled events, but new reveals are blocked. Unarchiving restores event operations only when the event is not cancelled.
- Gift prices support EUR and PLN. A known price requires an explicit currency. Gift prices and event budgets use two decimal places and must be between 0 and 999,999.99 inclusive.
- Initial configurable limits are 100 roster entries per event, 200 gifts per wishlist, 120 characters per name, 2,000 characters per description, and 2,048 characters per URL. These are server-side limits, not just form constraints.
- Sessions expire after seven days, verification tokens after 24 hours, and password-reset tokens after 30 minutes. Verification/reset tokens are single-use. Invite links remain valid until revoked or regenerated, subject to event-state restrictions.
- Account deletion removes personal profile/wishlist data and anonymizes historical roster names associated with the account. Retained identity labels become a neutral deleted-user label.
- Backups expire within 30 days. Deletion records are reapplied when restoring backups before reopening access; immediate physical erasure from existing backups is not promised.
