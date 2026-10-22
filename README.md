# AGN Global News — private staging preparation

The editable application now lives in `services/api`; staging configuration is in
`infra/staging`. The original v0.2 ZIP is an archived local-development edition,
not the staging deployment source.

**Do not deploy publicly.** This branch prepares a single-administrator private
staging environment. It is not a production release, automated news service, or
mobile application. All original demonstrations remain labeled as demos.

## What changed

- Staging replaces the shared development bearer token with scrypt password
  verification and one-hour server-side sessions. Cookies are Secure, HttpOnly,
  SameSite Strict. Mutations require a session-bound CSRF token. Login attempts
  are throttled. Logout invalidates the session. Session state is deliberately
  in memory: use exactly one API process; restarts log everyone out.
- PostgreSQL and API have no published ports. Only Caddy's HTTPS endpoint is
  published, on **127.0.0.1:8443**. An SSH tunnel is required for remote access;
  no public DNS change is required. Staging pages send noindex and no-store.
- Staging reads database credentials and the admin password hash from secret
  files. Its non-root API has a read-only filesystem. API documentation is
  disabled in staging. Development mode remains local-only.
- Encrypted PostgreSQL dumps are generated on backup-container startup and
  every 24 hours. An isolated disposable-container restore check is included.
- Python dependencies are pinned in `requirements.lock` for the tested build.
  Container image tags still need digest pinning before deployment acceptance.

## Operator setup — no steps have been run on a hosting account

These instructions are for the deployment operator. The owner does not need to
write code or share passwords in chat. A suitable VPS and an authorized secure
server connection are still required. Do not reinstall an existing server.

1. Review this branch; confirm a clean, isolated staging VPS with Docker Compose,
   an SSH account using key authentication and a verified SSH host key. Restrict
   SSH ingress to authorized operators. Snapshot any existing server first.
2. On that server run `sudo python3 scripts/prepare_staging.py`. Enter the new
   administrator password privately at its terminal prompt. This creates unique
   database and backup secrets and refuses to overwrite existing credentials.
   Keep the backup passphrase separately in a password manager. Do not commit,
   print in logs, or transmit the contents of `infra/staging/secrets` in chat.
3. From `infra/staging`, run `docker compose -f compose.yml config --quiet`, then
   `docker compose -f compose.yml up -d --build`. This creates a NEW named staging
   volume. It must never point to a production database. Do not use `down -v`.
4. Retrieve Caddy's local root certificate using an authenticated server channel:
   `docker compose -f compose.yml cp https:/data/caddy/pki/authorities/local/root.crt ./staging-root.crt`.
   Verify its fingerprint with the operator before explicitly trusting this
   private staging CA on the review device. Never bypass a browser certificate
   warning or copy Caddy's private CA key. A publicly trusted certificate is NOT
   provisioned here; this is private HTTPS with an explicitly trusted local CA.
5. Establish a local SSH forward:
   `ssh -N -L 127.0.0.1:8443:127.0.0.1:8443 operator@VERIFIED_SERVER`.
   Open `https://localhost:8443/en` and `/studio`, using username `admin` and the
   privately entered password. The hostname/port must remain as configured.
6. Verify all services are healthy, login/logout work, wrong passwords fail,
   unauthenticated publishing fails, and no remote public interface exposes
   ports 8000, 5432 or 8443. Docker-published ports must be checked independently
   of the host firewall. Confirm staging pages cannot be reached without SSH.
7. Run a fresh backup with
   `docker compose -f compose.yml run --rm backup --once`, then execute
   `scripts/restore_staging.sh /absolute/path/to/backup.dump.gpg` from the project
   root. It restores into an isolated disposable PostgreSQL container, checks
   the editions table, and removes the test container. Do not accept backups
   until an actual encrypted restore succeeds.
8. Arrange encrypted off-server copies and retention (for example 7 daily and
   4 weekly backups), disk-space alerts, failure alerts, and provider snapshots.
   Local encrypted backups alone do not protect against loss of the VPS. No
   automatic pruning is included: monitor capacity and add retention before
   unattended long-term use.

## Verification and remaining limits

Run `python -m pip install -r requirements.lock` then `python -m pytest -q`
from `services/api`. Local tests use SQLite, including the staged-auth app test;
they do not prove PostgreSQL compatibility or Docker networking/TLS/backups.

Docker build, PostgreSQL smoke tests, certificate trust, external port checks,
and an actual restore must pass on a Docker-capable environment before staging
is accepted. No server or DNS has been changed by this work.

Database tables still use prototype `create_all` on first startup. Existing
schema upgrades and production migrations are not supported. Use a fresh
staging database only. SSO/MFA, multiple roles, durable identity-based audit for
all actions, production migrations, accessibility/browser QA, and security
review remain before public release. Publication still requires human facts,
provenance, and rights review. There are no licensed feeds or AI auto-publishing.

The Windows launcher and `infra/docker-compose.yml` are retained for original
local development only. They must not be used as VPS staging configuration.


## Render staging proposal (not applied)

`render.yaml` proposes one free Docker web service and the smallest paid
PostgreSQL compute plan with 1 GB storage, both in Singapore. Auto-deployment
and database storage autoscaling are disabled. Database external connections
are blocked with an empty IP allow list; the application uses the internal URL.
The free web service can sleep and restart, which invalidates in-memory sessions.
Upgrade decisions require separate owner approval.

This differs from the VPS tunnel: Render exposes an HTTPS sign-in page publicly,
but all news pages, article APIs and editorial APIs require authentication.
Only sign-in, session/logout handlers, static sign-in styles and health checks
are accessible before authentication. This is application-restricted staging,
not network-private hosting. It must not be described as a public news launch.

Render generates `STAGING_ADMIN_PASSWORD`; it is never checked into GitHub or
sent in chat. Retrieve it privately in the service Environment settings when
signing in as `admin`. The app derives an scrypt hash in memory at startup.
The app refuses Render startup unless staging and whole-site protection are
explicitly enabled. PostgreSQL URLs are normalized to the psycopg driver.

Paid Render PostgreSQL includes point-in-time recovery (3 days on Hobby,
7 days on Pro or higher). Validate the actual recovery settings and restore
path after provisioning. Off-provider archival copies remain a separate task.
The VPS backup container is not automatically deployed by this Blueprint.

Estimated baseline: $0 free web compute + $6/month database compute + up to
$0.30/month for 1 GB database storage (confirm any included storage credit).
Taxes, exchange rates and overage charges are additional; this is not a hard
spending cap. No paid workspace upgrade, custom domain or DNS change is proposed.
Do not apply until the owner approves billing and the public sign-in surface.

The proposed changes remain on `staging-preparation` in draft PR #1. Render
Blueprint setup must explicitly use that branch; default main still contains
the original archive. Do not use the generic default-branch deployment link.
Blueprint application and platform-aware validation have not been run. Schema
validation and tests are recorded in the pull request. A Render deployment must
still be inspected for healthy startup, inaccessible unauthenticated content,
secure cookies, generated credentials and internal-only database connectivity.
