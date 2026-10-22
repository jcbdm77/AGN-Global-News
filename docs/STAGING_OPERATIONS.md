# AGN staging operations

Staging uses the free Render Docker web service and the paid 1 GB PostgreSQL instance in Singapore. Automatic deployments and Blueprint sync remain disabled. Keep this environment authenticated; it is not a public news launch.

## Database migrations

Startup runs the checked-in Alembic revisions in one transaction. PostgreSQL uses a transaction-scoped advisory lock and a ten-second lock timeout. The initial adoption compares the existing schema with the frozen initial revision and refuses unknown or incomplete schemas. Existing articles are not rebuilt or copied. Do not stamp revisions manually to bypass a mismatch. Test subsequent schema revisions against a restored backup before deployment.

The /ready endpoint verifies database connectivity and the current migration revision. Render already monitors this endpoint. /health is a process liveness check and does not prove database readiness. No custom email/SMS alert recipient has been configured; account notification settings determine delivery of Render notices. Free service sleep and in-memory session resets remain expected.

## Deployment and rollback

Run all API tests and the private staging CI workflow before triggering a manual Render deploy. Preserve a fresh database export before any destructive schema change. Roll back application code only to a version compatible with the current database schema. Destructive migration downgrades are deliberately disabled; recovery requires a separately reviewed plan and a tested backup.

## Backups

Render's Recovery page confirmed a three-day recovery window and a completed export on 23 October 2026. The exported archive was downloaded privately and its schema/data restored into isolated embedded PostgreSQL. The CI workflow also creates an encrypted backup and restores it into disposable native PostgreSQL 16 using disposable data. A Render-managed point-in-time restore has not been executed.

Scheduled off-provider backups are not configured: a private destination and narrowly scoped upload credentials are still needed. Do not open external database access or place a backup or signed download URL in GitHub to work around this. Existing VPS backup scripts apply only to that separate Docker Compose topology, not to the Render database.

## Remaining launch requirements

Individual identities, role-based permissions, MFA/account recovery, durable sessions, monitoring alert delivery, scheduled off-provider backups, and editorial/legal review are still required before a production release. No custom DNS, public news launch, mobile-store submission, or new paid service is authorized by this configuration.
