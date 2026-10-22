[README.md](https://github.com/user-attachments/files/33839693/README.md)
# AGN Global News — Version 0.2 (local development prototype)

A single-service AGN global news website, FastAPI news backend, PostgreSQL database, and editorial studio. Eight language filters: English, Telugu, Hindi, Tamil, Kannada, Malayalam, Marathi, Urdu. Contains one **explicitly labeled demonstration article**, not current news.

## Windows: easiest launch

1. Install and start Docker Desktop.
2. Extract this ZIP anywhere on Windows.
3. Double-click **START_AGN_WINDOWS.bat**. The launcher creates private local secrets in `infra/.env` on first run and starts Docker Compose. Never send those secrets to anyone.
4. In Chrome open http://localhost:8000/en (news portal) and http://localhost:8000/studio (admin).
5. To unlock Studio: use Notepad to open `infra/.env`, copy only the value to the right of `ADMIN_TOKEN=`, and paste it into Studio's token field. This is a development access control, **not production authentication**.
6. Click **+ New Article**, write an original sourced demo draft, save it, then **Review & Publish** after confirming each editorial attestation. The story appears on the news page for its language.
7. Keep the launcher command window open while using AGN. To stop, press Ctrl+C and confirm.

If Docker Compose reports port 8000 is already allocated (e.g. because v0.1 is still running), stop the old version first. From your old `infra` folder run `docker compose down` (without `-v`, which would delete its database volume).

## Endpoints

- News website: `http://localhost:8000/en`
- Editorial dashboard: `http://localhost:8000/studio`
- Swagger API: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Public API: `GET /v1/articles?locale=en`, `GET /v1/articles/{locale}/{slug}`
- Protected editor API: `GET /v1/editor/editions`, `GET /v1/editor/editions/{id}`, `GET /v1/editor/stats`, `GET /v1/editor/audit`, `POST /v1/editor/drafts`, `PUT /v1/editor/editions/{id}`, `POST /v1/editor/editions/{id}/publish`, `POST /v1/editor/editions/{id}/retract`.

## Important limitations and next milestones

This is a local prototype. **Do not expose it to the public internet.** It does not include production-grade authentication, complete SEO internationalization, news licensing connectors, AI generation, independent translation validation, real push notifications, mobile app, subscriptions, proper migrations or distributed scaling. Automated AI-generated news is deliberately disabled; actual news must pass provenance, accuracy and rights checks. The initial demo is explicitly fictional, and translation editions are manually created. SEO basics include simple canonical article pages, structured data, robots.txt and sitemap.xml; no claim of Google News eligibility is made.

Production roadmap: secrets vault, SSO/MFA/RBAC, versioned migrations, ownership and copyright verification workflows, journalist role, localization pipeline, trusted licensed feeds, AI draft assistants with evidence extraction, legal/editorial review, logging, backups, CI/CD and managed hosting, then Flutter Android/iOS apps. The v0.1 project is archived separately; v0.2 is intentionally a **simpler independent single-server edition**, not an in-place schema migration.

## Run tests

From `services/api`: `pip install -r requirements.txt` and `python -m pytest -q`. Tests use in-memory SQLite and do not need Docker. The Docker service starts with `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
