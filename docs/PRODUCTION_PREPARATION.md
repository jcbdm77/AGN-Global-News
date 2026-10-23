# Production candidate — not deployed

This change prepares a production mode. It does not launch the site, provision
resources, change DNS, publish reporting, or complete the recovery drill.

## Access boundaries

- `APP_ENV=production` uses the same durable staff accounts, hashed sessions,
  CSRF checks, role permissions and authenticated audit actors as staging.
- PostgreSQL, an administrator secret and a valid persistent MFA encryption key
  are required. Production does not seed sample news.
- The website remains private by default. A public reader requires both
  `PUBLIC_READER_ENABLED=true` and `PUBLIC_LAUNCH_APPROVAL=approved`, plus a clean
  HTTPS origin in `PUBLIC_BASE_URL`. Set these only after the owner's explicit
  final launch approval.
- Public access is limited to reader GET/HEAD routes. Editorial APIs, staff
  management, internal assets and API documentation remain protected. Newsroom
  access requires MFA. An owner without MFA can sign in to enroll it, but cannot
  access editorial data or publish.
- Production reader queries and sitemap omit demo stories. Drafts and retracted
  stories remain inaccessible to anonymous readers. Private pages retain
  `noindex` and all managed responses retain `no-store`.

## Operator preparation

Use `infra/production.env.example` only as an unpopulated review template.
Retained `STAGING_ADMIN_*` variable names are compatibility names, not a reason
to copy development credentials. Never commit populated values. Use a separate
production database and securely supplied credentials; do not point a production
candidate at the existing staging database. Preserve the MFA key corresponding
to any restored accounts. Changing that key prevents existing factors decrypting.

Existing `render.yaml` still describes private staging and is unchanged.
Automatic deployment remains off. The current live release is unchanged.

## Remaining launch gates

- Validate this candidate on isolated native PostgreSQL and HTTPS hosting.
- Complete the real saved-key MFA recovery sign-in test. The embedded database
  restore is useful evidence but does not complete this check.
- Verify the first scheduled off-provider backup and its failure reporting.
  The current ChatGPT task depends on account/browser access and is not an
  infrastructure backup guarantee.
- Confirm production hosting capacity and cost, final domain, publisher/contact
  details, privacy/editorial policies, and final reader copy. Current frontend
  still identifies the product as a prototype; it is not a reviewed public launch.
- Obtain explicit approval before public exposure, paid provisioning, DNS changes
  or publishing reporting. Mobile applications remain separate work.

## Verification

`services/api/tests/test_production.py` uses disposable secrets and isolated
SQLite fixtures to exercise private defaults, explicit launch gating, public
reader boundaries, demo/draft exclusion, MFA before editorial access, and audit
identity. These are application tests, not a native Render production drill.
