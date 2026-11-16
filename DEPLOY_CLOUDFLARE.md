# Deploying ESCALATE™ to Cloudflare Workers + Assets + D1

This adapts the product to Cloudflare's edge runtime. The original Python/FastAPI + Cloud Run path remains for the Google ADK / Vertex path. The Cloudflare path uses Hono, Workers Assets for the operator console, and D1 (SQLite) for persistence.

## Prerequisites

- Cloudflare account
- Wrangler CLI: `npm i -g wrangler`
- Authenticated: `wrangler login`

## Setup

```bash
cd cloudflare
npm install
# Create D1 database and paste the id into wrangler.toml
npx wrangler d1 create escalate-d1
# Apply migrations (create the SQL files under migrations/ first)
npx wrangler d1 migrations apply escalate-d1
```

## Local development

```bash
npx wrangler dev
```

Opens the operator console with `/health` and `/v1/me` working. Static files from `../frontend` are served via Assets.

## Deploy

```bash
npx wrangler deploy
```

## Architecture notes

- **Frontend**: Workers Assets (same `frontend/` directory). No separate Pages project needed.
- **API**: Hono on Workers. Port remaining FastAPI routes incrementally; start with the demo store shape.
- **Persistence**: D1. Schema should mirror the Postgres migrations in `schemas/migrations/` (SQLite dialect). Enforce tenant isolation with `workspace_id` / `org_id` filters in every query.
- **LLM**: Use Cloudflare AI Gateway in front of Gemini, or Workers AI. The ADK agent path stays on the GCP deploy.
- **Invariants**: Keep AVE disabled, human-must-send, and listed-issuer rules in the data layer, same as the Python validators.

## Next steps for a full port

1. Port domain models and seed data to TypeScript.
2. Implement war-rooms, mentions, holdings, evaluation routes against D1.
3. Add Durable Object or KV for any session / lock state if needed.
4. Wire AI Gateway for the holding drafter.
5. Add Queues for any async report or connector work.

See also the original `DEPLOY_CLOUD_RUN.md` for the GCP path.
