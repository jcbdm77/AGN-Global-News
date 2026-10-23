# AGN staging operations

Staging uses the free Render Docker web service and the paid 1 GB PostgreSQL instance in Singapore. Automatic deployments and Blueprint sync remain disabled. Keep this environment authenticated; it is not a public news launch.

## Database migrations

Startup runs the checked-in Alembic revisions in one transaction. PostgreSQL uses a transaction-scoped advisory lock and a ten-second lock timeout. The initial adoption compares the existing schema with the frozen initial revision and refuses unknown or incomplete schemas. Existing articles are not rebuilt or copied. Do not stamp revisions manually to bypass a mismatch. Test subsequent schema revisions against a restored backup before deployment.

The /ready endpoint verifies database connectivity and the current migration revision. Render already monitors this endpoint. /health is a process liveness check and does not prove database readiness. No custom email/SMS alert recipient has been configured; account notification settings determine delivery of Render notices. Free service sleep remains expected. Sessions and failed-login throttles now persist in PostgreSQL. Session cookies expire after one hour; changing the configured administrator credential invalidates them. Only token hashes are stored.

## Deployment and rollback

Run all API tests and the private staging CI workflow before triggering a manual Render deploy. Preserve a fresh database export before any destructive schema change. Roll back application code only to a version compatible with the current database schema. Destructive migration downgrades are deliberately disabled; recovery requires a separately reviewed plan and a tested backup.

## Backups

Render's Recovery page confirmed a three-day recovery window and a completed export on 23 October 2026. The exported archive was downloaded privately and its schema/data restored into isolated embedded PostgreSQL. The CI workflow also creates an encrypted backup and restores it into disposable native PostgreSQL 16 using disposable data. A Render-managed point-in-time restore has not been executed.

Scheduled off-provider backups are not configured: a private destination and narrowly scoped upload credentials are still needed. Do not open external database access or place a backup or signed download URL in GitHub to work around this. Existing VPS backup scripts apply only to that separate Docker Compose topology, not to the Render database.

## Remaining launch requirements

Owner MFA enrollment, final staff access review, monitoring alert delivery, scheduled off-provider backups, and editorial/legal review are still required before a production release. No custom DNS, public news launch, mobile-store submission, or new paid service is authorized by this configuration.

## Named accounts and MFA

The existing owner account remains the bootstrap administrator. Visit Studio → Account security & staff, enter the owner password, add the private setup key to an authenticator, and confirm a fresh code. Save the ten one-use recovery codes privately; they are shown once. Confirmation revokes existing sessions, so sign in again using a new authenticator code (wait for the next 30-second code) or an unused recovery code. Owner enrollment is not performed automatically by deployment.

Owner MFA is required before inviting, disabling or resetting staff. Each management action requires the owner password and a fresh MFA code or unused recovery code. An invitation lasts 24 hours and its secret is stored only as a hash. Staff choose a password of at least 16 characters and must enroll an authenticator before activation. Staff cannot invite other staff or grant owner permissions. The app does not send invitation emails; the owner shares activation links through a verified private channel. Reset access revokes sessions and old factors, disables the account, and produces a new one-use activation link.

Editors create/edit drafts, reviewers publish/retract, and viewers read. The owner can perform all editorial actions. Backend checks enforce these permissions even if someone alters browser controls.

AUTH_ENCRYPTION_KEY encrypts authenticator secrets. Preserve this key privately and separately from database exports. Losing it prevents MFA decryption; do not overwrite it during a redeploy. An environment key change is not a safe rotation procedure. Restore tests for encrypted MFA data require the original key. Recovery codes are hashed, consumed atomically, and always require the password; OTP counters reject replay. Login and enrollment confirmation are throttled. Owner recovery requires the saved recovery codes or an independently reviewed server recovery procedure; there is no unauthenticated bypass.

The staff/MFA acceptance suite runs with disposable credentials against SQLite and native PostgreSQL in CI. It never enrolls the real owner or creates real staff accounts on Render.
