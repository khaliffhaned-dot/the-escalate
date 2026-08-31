# The Escalate

**A governed crisis-response desk for Malaysian PR teams.** It watches the
conversation, escalates 3R-sensitive incidents into a war room, and drafts a
bilingual holding statement with a Google ADK agent that *structurally cannot
send it alone*.

Built for the **All Things Agentic Hackathon** (Google).

> *Internal package name remains `nadi`. Imports and CLI commands below use it.*

- **Barcelona Principles 4.0** evaluation — AVE/EMV is rejected at four layers,
  not merely discouraged
- **Google ADK agent** with scoped tools and a Pydantic-constrained output schema
- **Human-must-send** holding statements — no auto-publish path exists
- **3R** (Royalty · Religion · Race) risk flagging, tuned for the Malaysian market
- Tenant/RBAC permission matrix, Postgres RLS migration, weekly executive briefs

---

## Quick start (local)

**Requires Python 3.11+.** No API keys or Google Cloud account needed — the app
runs fully offline against a deterministic drafting path and seeded demo data.

```bash
git clone <your-repo-url> the-escalate && cd the-escalate
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
uvicorn nadi.api.app:app --port 8080
```

Then open **<http://127.0.0.1:8080>** — the operator console is served from the
same origin as the API.

| URL | What it is |
|-----|------------|
| <http://127.0.0.1:8080> | Operator console (Dashboard, Mentions, Evaluation, War Rooms, Holdings) |
| <http://127.0.0.1:8080/docs> | OpenAPI / Swagger UI |
| <http://127.0.0.1:8080/health> | Liveness probe |

Demo workspace id: `ws_aurora`. Switch roles with the dropdown at the bottom
of the sidebar to watch the permission matrix take effect live.

### Run the tests

```bash
pip install -e ".[dev]"
pytest -q
```

66 tests. They run offline and need no credentials.

---

## Enabling the live Gemini agent

Without credentials the app uses a deterministic drafting path, so the demo
always works. Provide **either** of the following to route drafting through the
real Google ADK agent instead:

```bash
# Option A — Vertex AI on Google Cloud (what the Cloud Run deploy uses)
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project-id

# Option B — Gemini API key
export GEMINI_API_KEY=your-key
```

Restart the server. Drafts produced by the agent are stamped
`model_version: adk:gemini-3.5-flash`; the offline path is stamped
`nadi-brief-2026-08-local`, so you can always tell which one ran.

### Configuration

All settings take a `NADI_` prefix and may also come from a `.env` file.

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_CLOUD_PROJECT` | *unset* | Routes Gemini through Vertex AI (ADC auth) |
| `GEMINI_API_KEY` | *unset* | Direct Gemini API key |
| `NADI_GCP_LOCATION` | `asia-southeast1` | Vertex AI region |
| `NADI_LLM_MODEL` | `gemini-3.5-flash` | Model id |
| `NADI_LLM_PROVIDER` | `auto` | `adk` · `vertex` · `gemini` · `openai` · `mock` |
| `NADI_USE_DB_STORE` | `false` | Use Postgres/SQLite instead of the in-memory demo store |
| `NADI_DATABASE_URL` | `sqlite:///./nadi.db` | Database connection string |
| `PORT` | `8080` | Injected by Cloud Run; do not hardcode |

`NADI_AVE_ENABLED` exists but is inert by design — see
[Product invariants](#product-invariants).

---

## Deploy to Cloud Run

Builds remotely with Cloud Build, so **no local Docker is required**.

```bash
gcloud run deploy the-escalate --source . --region asia-southeast1 --allow-unauthenticated --set-env-vars GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project) --min-instances 0 --max-instances 2 --memory 512Mi
```

The service account needs the **Vertex AI User** role for the agent path to
work. Cost-conscious defaults (`--min-instances 0`) mean the service scales to
zero when idle. Full walkthrough and troubleshooting: [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md).

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full diagram and the
reasoning behind each boundary.

```
frontend/            Operator console (vanilla JS), served at "/" by the API
src/nadi/
  api/               FastAPI app, routes, RBAC dependency injection
  services/
    adk_holding_agent.py   Google ADK agent — scoped tools, Pydantic output schema
    llm_holding.py         Provider selection + the shared text guards
    holding_service.py     Deterministic path, AVE regex, state machine
    evaluation_service.py  AMEC IEF scoring
    reporting_service.py   Executive brief compilation + HTML
    scheduler.py           Weekly report scheduling
  connectors/        RSS, social, Telegram ingest + pipeline
  domain/            Enums, Pydantic models, RBAC matrix
  db/                SQLAlchemy models, repository, session
  data/              Aurora / Jalur Kita demo seed
schemas/migrations/  Postgres schema + row-level security
```

### Key routes

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/v1/workspaces/{ws}/mentions` | Ingested mentions with 3R flags |
| `GET` | `/v1/workspaces/{ws}/evaluation` | Live AMEC IEF evaluation |
| `POST` | `/v1/workspaces/{ws}/evaluation/lock` | Lock snapshot — rejects `include_ave` |
| `GET` | `/v1/workspaces/{ws}/war-rooms` | Crisis canvas |
| `POST` | `/v1/workspaces/{ws}/briefs` | `{"kind":"holding","mention_ids":[...]}` |
| `POST` | `/v1/workspaces/{ws}/holdings/{id}/transition` | draft → approved → sent_external |
| `GET` | `/v1/workspaces/{ws}/reports/preview?snapshot_id=...` | Executive brief HTML |
| `POST` | `/v1/workspaces/{ws}/reports/schedule` | Register a weekly brief |

Auth in the demo is a header: `X-Nadi-Role: ws_admin`. Roles are `ws_admin`,
`editor`, `analyst`, `viewer`, `org_admin`, `org_auditor`.

---

## Product invariants

These are enforced in code and covered by tests, not left to prompt discipline:

1. **No AVE.** `ave_enabled` and `methodology.ave` are pinned `false` by Pydantic
   validators that ignore whatever value is passed. Requests carrying
   `include_ave` are rejected with HTTP 422. Generated prose is regex-scanned,
   and a draft containing AVE language is discarded in favour of a safe one.
2. **Holdings never auto-publish.** `human_must_send` is forced `true` and
   `auto_publish` forced `false` on every provider path, including the agent's.
   Reaching `sent_external` requires an explicit human state transition.
3. **Evaluation weights** are fixed: outputs 15 · outtakes 25 · outcomes 35 ·
   impact 25.
4. **Exactly 3 board moves** on snapshot lock.
5. **Tabletop drafts are marked.** A simulation draft is prefixed
   `[TABLETOP — DO NOT SEND]` / `[TABLETOP — JANGAN HANTAR]` on every path, so a
   drill can never be mistaken for a sendable statement.

---

## Honest limitations

Stated plainly rather than buried:

- **The in-memory store is the default.** Cloud Run containers are ephemeral, so
  drafts and war-room state reset on restart unless `NADI_USE_DB_STORE=true` and
  a database is attached. The Postgres schema and RLS policies exist in
  `schemas/migrations/`; wiring Cloud SQL is a deploy-time step.
- **The scheduler has no in-process loop.** `POST /reports/schedules/run-due` is
  designed to be hit by an external timer (Cloud Scheduler), which is the
  correct shape for a scale-to-zero service but does mean nothing fires on its
  own until that trigger is configured.
- **Report delivery is not implemented.** Schedules compile the brief and record
  the run; SMTP/webhook dispatch is not wired.
- **Connectors ship with seeded data.** The RSS, social and Telegram connectors
  and their pipeline exist and are tested, but the demo runs on the Aurora /
  Jalur Kita seed rather than live ingest.
- **The live agent path needs credentials to observe.** Every layer up to the
  Google SDK boundary is tested offline, and the failure mode without
  credentials is a clean fallback rather than a crash — but the quality of a
  real Gemini-generated draft can only be judged with a live project attached.

---

## Licence

See repository settings.
